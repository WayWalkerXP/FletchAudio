"""Execution service for planned single-file audiobook conversions."""
from __future__ import annotations

import errno
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from .alchemist_engine.ffmpeg import (
    CommandResult,
    FFmpegAnalyzer,
    build_ffmpeg_command,
    run_external_command,
)
from .alchemist_engine.models import AudioInfo, ConversionPlan
from .alchemist_engine.validation import ValidationManager
from .audio_tags import write_audio_metadata
from .conversion_adapter import ConversionRequest, ConversionSettings
from .conversion_planner import ConversionPlanResult, plan_conversion


class ConversionStatus(str, Enum):
    """Terminal outcome of a conversion execution."""

    SUCCESS = "success"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class ConversionStage(str, Enum):
    """Observable stages emitted by the execution service."""

    PLANNING = "planning"
    PROBING = "probing"
    CONVERTING = "converting"
    VALIDATING = "validating"
    WRITING_METADATA = "writing_metadata"
    PROMOTING = "promoting"
    ARCHIVING = "archiving"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class ConversionProgressEvent:
    stage: str
    message: str
    source_path: Path
    temporary_output_path: Path | None = None
    final_output_path: Path | None = None


@dataclass(frozen=True)
class ConversionResult:
    status: ConversionStatus
    message: str
    source_path: Path
    temporary_output_path: Path | None = None
    final_output_path: Path | None = None
    archived_path: Path | None = None
    error_details: str | None = None


class Analyzer(Protocol):
    def probe(self, path: Path) -> AudioInfo: ...


class Validator(Protocol):
    def validate(
        self, source_info: AudioInfo, plan: ConversionPlan, output_path: Path
    ) -> bool: ...


ProgressCallback = Callable[[ConversionProgressEvent], None]
CommandRunner = Callable[[list[str]], CommandResult]
MetadataWriter = Callable[[str, dict], None]


class ConversionRunner:
    """Execute one conversion request while preserving the source on failure."""

    def __init__(
        self,
        settings: ConversionSettings,
        *,
        analyzer: Analyzer | None = None,
        validator: Validator | None = None,
        command_runner: CommandRunner = run_external_command,
        metadata_writer: MetadataWriter = write_audio_metadata,
    ) -> None:
        self.settings = settings
        self.analyzer = analyzer or FFmpegAnalyzer()
        self.validator = validator or ValidationManager(self.analyzer)
        self.command_runner = command_runner
        self.metadata_writer = metadata_writer

    def run(
        self,
        request: ConversionRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> ConversionResult:
        self._emit(progress_callback, ConversionStage.PLANNING, "Planning conversion", request.source_path)

        if request.is_folder_book:
            return self._failure(
                request.source_path,
                "Folder-book conversion is not supported",
                progress_callback,
                status=ConversionStatus.UNSUPPORTED,
            )

        plan_result = plan_conversion(request, self.settings)
        if plan_result.status != "planned":
            details = "; ".join(plan_result.errors) or "conversion plan is not executable"
            return self._failure(
                request.source_path,
                "Conversion planning failed",
                progress_callback,
                plan_result=plan_result,
                error_details=details,
            )

        if (
            plan_result.output_path is None
            or plan_result.temporary_output_path is None
            or plan_result.target_bitrate is None
            or plan_result.target_channels is None
            or plan_result.selected_codec is None
        ):
            return self._failure(
                request.source_path,
                "Conversion plan is incomplete",
                progress_callback,
                plan_result=plan_result,
            )

        engine_plan = self._engine_plan(plan_result)
        temporary_path = engine_plan.temporary_path

        try:
            self._emit_from_plan(progress_callback, ConversionStage.PROBING, "Probing source", plan_result)
            source_info = self.analyzer.probe(request.source_path)

            self._emit_from_plan(progress_callback, ConversionStage.CONVERTING, "Converting audio", plan_result)
            command = build_ffmpeg_command(
                request.source_path,
                temporary_path,
                engine_plan.codec,
                engine_plan.target_bitrate_kbps,
                engine_plan.output_channels,
            )
            command_result = self.command_runner(command)
            if command_result.returncode != 0:
                details = command_result.stderr.strip() or f"FFmpeg exited with code {command_result.returncode}"
                raise RuntimeError(details)

            self._emit_from_plan(progress_callback, ConversionStage.VALIDATING, "Validating converted output", plan_result)
            if not self.validator.validate(source_info, engine_plan, temporary_path):
                raise RuntimeError("converted output failed validation")

            self._emit_from_plan(
                progress_callback,
                ConversionStage.WRITING_METADATA,
                "Writing audiobook metadata",
                plan_result,
            )
            self.metadata_writer(str(temporary_path), dict(plan_result.metadata_summary))

            self._emit_from_plan(progress_callback, ConversionStage.PROMOTING, "Promoting converted output", plan_result)
            _promote_without_overwrite(temporary_path, engine_plan.final_path)

            archived_path: Path | None = None
            if self.settings.archive_original and plan_result.archive_path is not None:
                self._emit_from_plan(progress_callback, ConversionStage.ARCHIVING, "Archiving original source", plan_result)
                _move_without_overwrite(request.source_path, plan_result.archive_path)
                archived_path = plan_result.archive_path

            self._emit_from_plan(progress_callback, ConversionStage.COMPLETE, "Conversion complete", plan_result)
            return ConversionResult(
                status=ConversionStatus.SUCCESS,
                message="Conversion completed successfully",
                source_path=request.source_path,
                temporary_output_path=temporary_path,
                final_output_path=engine_plan.final_path,
                archived_path=archived_path,
            )
        except Exception as exc:
            _remove_temporary_output(temporary_path)
            return self._failure(
                request.source_path,
                "Conversion failed",
                progress_callback,
                plan_result=plan_result,
                error_details=str(exc),
            )

    @staticmethod
    def _engine_plan(plan: ConversionPlanResult) -> ConversionPlan:
        assert plan.output_path is not None
        assert plan.temporary_output_path is not None
        assert plan.target_bitrate is not None
        assert plan.target_channels is not None
        assert plan.selected_codec is not None
        return ConversionPlan(
            source_path=plan.source_path,
            final_path=plan.output_path,
            temporary_path=plan.temporary_output_path,
            archive_path=plan.archive_path or plan.source_path,
            target_bitrate_kbps=plan.target_bitrate,
            output_channels=plan.target_channels,
            codec=plan.selected_codec,
            output_metadata=dict(plan.metadata_summary),
            write_final_metadata=True,
            dramatic_audio_output=plan.dramatic_audio_output,
        )

    def _failure(
        self,
        source_path: Path,
        message: str,
        callback: ProgressCallback | None,
        *,
        status: ConversionStatus = ConversionStatus.FAILED,
        plan_result: ConversionPlanResult | None = None,
        error_details: str | None = None,
    ) -> ConversionResult:
        temporary_path = plan_result.temporary_output_path if plan_result else None
        final_path = plan_result.output_path if plan_result else None
        self._emit(
            callback,
            ConversionStage.FAILED,
            error_details or message,
            source_path,
            temporary_path,
            final_path,
        )
        return ConversionResult(
            status=status,
            message=message,
            source_path=source_path,
            temporary_output_path=temporary_path,
            final_output_path=final_path,
            error_details=error_details,
        )

    @staticmethod
    def _emit_from_plan(
        callback: ProgressCallback | None,
        stage: ConversionStage,
        message: str,
        plan: ConversionPlanResult,
    ) -> None:
        ConversionRunner._emit(
            callback,
            stage,
            message,
            plan.source_path,
            plan.temporary_output_path,
            plan.output_path,
        )

    @staticmethod
    def _emit(
        callback: ProgressCallback | None,
        stage: ConversionStage,
        message: str,
        source_path: Path,
        temporary_path: Path | None = None,
        final_path: Path | None = None,
    ) -> None:
        if callback is not None:
            try:
                callback(
                    ConversionProgressEvent(
                        stage=stage.value,
                        message=message,
                        source_path=source_path,
                        temporary_output_path=temporary_path,
                        final_output_path=final_path,
                    )
                )
            except Exception:
                # Progress reporting is observational and must not alter the
                # filesystem transaction or its result.
                pass


def run_conversion(
    request: ConversionRequest,
    settings: ConversionSettings,
    progress_callback: ProgressCallback | None = None,
) -> ConversionResult:
    """Execute a single-file conversion with default engine dependencies."""
    return ConversionRunner(settings).run(request, progress_callback)


execute_conversion = run_conversion


def _promote_without_overwrite(temporary_path: Path, final_path: Path) -> None:
    """Promote a validated file without ever replacing an existing destination."""
    try:
        os.link(temporary_path, final_path)
    except OSError as exc:
        if exc.errno == errno.EEXIST or final_path.exists():
            raise FileExistsError(f"destination already exists: {final_path}") from exc
        if exc.errno not in {errno.EXDEV, errno.EPERM, errno.EACCES, errno.ENOTSUP}:
            raise
        destination_created = False
        try:
            with temporary_path.open("rb") as source:
                with final_path.open("xb") as destination:
                    destination_created = True
                    shutil.copyfileobj(source, destination)
        except Exception:
            if destination_created:
                final_path.unlink(missing_ok=True)
            raise
    temporary_path.unlink()


def _move_without_overwrite(source_path: Path, destination_path: Path) -> None:
    _promote_without_overwrite(source_path, destination_path)


def _remove_temporary_output(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
