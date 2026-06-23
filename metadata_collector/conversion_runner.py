"""Execution service for planned single-file audiobook conversions."""
from __future__ import annotations

import errno
import logging
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
from .audio_tags import copy_embedded_cover_art, write_audio_metadata
from .conversion_adapter import ConversionRequest, ConversionSettings
from .conversion_archive import archive_source_file
from .conversion_planner import ConversionPlanResult, plan_conversion

LOGGER = logging.getLogger(__name__)
MAX_USER_FACING_ERROR_DETAILS = 1200


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
CoverCopier = Callable[[str, str], bool]
ArchiveMover = Callable[[Path, Path], Path]


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
        cover_copier: CoverCopier = copy_embedded_cover_art,
        archive_mover: ArchiveMover = archive_source_file,
    ) -> None:
        self.settings = settings
        self.analyzer = analyzer or FFmpegAnalyzer()
        self.validator = validator or ValidationManager(self.analyzer)
        self.command_runner = command_runner
        self.metadata_writer = metadata_writer
        self.cover_copier = cover_copier
        self.archive_mover = archive_mover

    def run(
        self,
        request: ConversionRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> ConversionResult:
        self._emit(progress_callback, ConversionStage.PLANNING, "Planning conversion", request.source_path)
        if self.settings.archive_original and self.settings.processed_dir is not None:
            LOGGER.info("Archive directory configured: %s", self.settings.processed_dir)

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
            self._validate_execution_paths(request.source_path, temporary_path, engine_plan.final_path)
            self._emit_from_plan(progress_callback, ConversionStage.PROBING, "Probing source", plan_result)
            LOGGER.info(
                "Conversion probing source=%s destination=%s temporary=%s ffprobe=%s",
                request.source_path,
                engine_plan.final_path,
                temporary_path,
                shutil.which("ffprobe"),
            )
            source_info = self.analyzer.probe(request.source_path)

            self._emit_from_plan(progress_callback, ConversionStage.CONVERTING, "Converting audio", plan_result)
            command = build_ffmpeg_command(
                request.source_path,
                temporary_path,
                engine_plan.codec,
                engine_plan.target_bitrate_kbps,
                engine_plan.output_channels,
            )
            LOGGER.info(
                "Conversion command source=%s destination=%s temporary=%s executable=%s resolved=%s command=%r",
                request.source_path,
                engine_plan.final_path,
                temporary_path,
                command[0] if command else None,
                shutil.which(command[0]) if command else None,
                command,
            )
            command_result = self.command_runner(command)
            if command_result.returncode != 0:
                LOGGER.error(
                    "Conversion command failed source=%s destination=%s executable=%s resolved=%s returncode=%s stderr=%r",
                    request.source_path,
                    engine_plan.final_path,
                    command[0] if command else None,
                    shutil.which(command[0]) if command else None,
                    command_result.returncode,
                    command_result.stderr,
                )
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
            try:
                copied_cover = self.cover_copier(str(request.source_path), str(temporary_path))
                LOGGER.info(
                    "Conversion embedded cover copy source=%s temporary=%s copied=%s",
                    request.source_path,
                    temporary_path,
                    copied_cover,
                )
            except Exception as exc:
                LOGGER.warning(
                    "Conversion embedded cover copy failed source=%s temporary=%s original_exception=%r",
                    request.source_path,
                    temporary_path,
                    exc,
                )

            self._emit_from_plan(progress_callback, ConversionStage.PROMOTING, "Promoting converted output", plan_result)
            _promote_without_overwrite(temporary_path, engine_plan.final_path)

            archived_path: Path | None = None
            message = "Conversion completed successfully"
            archive_warning: str | None = None
            if self.settings.archive_original and plan_result.archive_path is not None:
                self._emit_from_plan(progress_callback, ConversionStage.ARCHIVING, "Archiving original source", plan_result)
                try:
                    archived_path = self.archive_mover(request.source_path, plan_result.archive_path.parent)
                    LOGGER.info(
                        "Archived original file:\n%s -> %s",
                        request.source_path,
                        archived_path,
                    )
                except Exception as exc:
                    archive_warning = (
                        "Conversion completed successfully, but the original file "
                        "could not be moved to the Archive Directory."
                    )
                    message = archive_warning
                    LOGGER.error(
                        "Failed to archive original file:\n%s\nReason: %r",
                        request.source_path,
                        exc,
                    )

            self._emit_from_plan(progress_callback, ConversionStage.COMPLETE, "Conversion complete", plan_result)
            return ConversionResult(
                status=ConversionStatus.SUCCESS,
                message=message,
                source_path=request.source_path,
                temporary_output_path=temporary_path,
                final_output_path=engine_plan.final_path,
                archived_path=archived_path,
                error_details=archive_warning,
            )
        except Exception as exc:
            LOGGER.error(
                "Conversion failed source=%s destination=%s temporary=%s original_exception=%r",
                request.source_path,
                engine_plan.final_path,
                temporary_path,
                exc,
            )
            _remove_temporary_output(temporary_path)
            return self._failure(
                request.source_path,
                "Conversion failed",
                progress_callback,
                plan_result=plan_result,
                error_details=_user_facing_error_details(str(exc)),
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
    def _validate_execution_paths(source_path: Path, temporary_path: Path, final_path: Path) -> None:
        if not source_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {source_path}")
        if not source_path.is_file():
            raise FileNotFoundError(f"Source path is not a file: {source_path}")
        for label, path in (("temporary output", temporary_path), ("destination", final_path)):
            parent = path.parent
            if not parent.exists():
                raise FileNotFoundError(f"{label} directory does not exist: {parent}")
            if not parent.is_dir():
                raise NotADirectoryError(f"{label} parent is not a directory: {parent}")

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


def _user_facing_error_details(details: str) -> str:
    if len(details) <= MAX_USER_FACING_ERROR_DETAILS:
        return details
    return f"{details[:MAX_USER_FACING_ERROR_DETAILS].rstrip()}… See logs for full details."


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
