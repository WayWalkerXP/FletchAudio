"""Execution service for planned audiobook conversions."""
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
    build_ffmpeg_concat_command,
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
        sidecar_paths: list[Path] = []

        try:
            self._validate_execution_paths(request, temporary_path, engine_plan.final_path)
            self._emit_from_plan(progress_callback, ConversionStage.PROBING, "Probing source", plan_result)
            LOGGER.info(
                "Conversion probing source=%s destination=%s temporary=%s ffprobe=%s",
                request.source_path,
                engine_plan.final_path,
                temporary_path,
                shutil.which("ffprobe"),
            )
            source_info, track_infos = self._probe_source(request, plan_result)

            self._emit_from_plan(progress_callback, ConversionStage.CONVERTING, "Converting audio", plan_result)
            if request.is_folder_book:
                concat_file, metadata_file = _write_folder_sidecars(
                    plan_result,
                    track_infos,
                    temporary_path.parent,
                    engine_plan.output_metadata,
                )
                sidecar_paths.extend((concat_file, metadata_file))
                command = build_ffmpeg_concat_command(
                    concat_file,
                    metadata_file,
                    temporary_path,
                    engine_plan.codec,
                    engine_plan.target_bitrate_kbps,
                    engine_plan.output_channels,
                )
            else:
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
                cover_source = str(plan_result.input_paths[0] if request.is_folder_book else request.source_path)
                copied_cover = self.cover_copier(cover_source, str(temporary_path))
                LOGGER.info(
                    "Conversion embedded cover copy source=%s temporary=%s copied=%s",
                    cover_source,
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
                        "Archived original source:\n%s -> %s",
                        request.source_path,
                        archived_path,
                    )
                except Exception as exc:
                    archive_warning = (
                        "Conversion completed successfully, but the original source "
                        "could not be moved to the Archive Directory."
                    )
                    message = archive_warning
                    LOGGER.error(
                        "Failed to archive original source:\n%s\nReason: %r",
                        request.source_path,
                        exc,
                    )

            self._emit_from_plan(progress_callback, ConversionStage.COMPLETE, "Conversion complete", plan_result)
            _remove_sidecars(sidecar_paths)
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
            _remove_sidecars(sidecar_paths)
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
    def _validate_execution_paths(request: ConversionRequest, temporary_path: Path, final_path: Path) -> None:
        source_path = request.source_path
        if not source_path.exists():
            label = "folder" if request.is_folder_book else "file"
            raise FileNotFoundError(f"Source {label} does not exist: {source_path}")
        if request.is_folder_book:
            if not source_path.is_dir():
                raise FileNotFoundError(f"Source path is not a folder: {source_path}")
        elif not source_path.is_file():
            raise FileNotFoundError(f"Source path is not a file: {source_path}")
        for input_path in request.files:
            if not input_path.is_file():
                raise FileNotFoundError(f"Input file does not exist: {input_path}")
        for label, path in (("temporary output", temporary_path), ("destination", final_path)):
            parent = path.parent
            if not parent.exists():
                raise FileNotFoundError(f"{label} directory does not exist: {parent}")
            if not parent.is_dir():
                raise NotADirectoryError(f"{label} parent is not a directory: {parent}")

    def _probe_source(
        self,
        request: ConversionRequest,
        plan_result: ConversionPlanResult,
    ) -> tuple[AudioInfo, tuple[AudioInfo, ...]]:
        if not request.is_folder_book:
            source_info = self.analyzer.probe(request.source_path)
            return source_info, (source_info,)
        track_infos = tuple(self.analyzer.probe(path) for path in plan_result.input_paths)
        if not track_infos:
            raise RuntimeError("folder-book has no readable audio tracks")
        first_info = track_infos[0]
        duration = sum(info.duration_seconds for info in track_infos)
        return (
            AudioInfo(
                path=request.source_path,
                bitrate_bps=first_info.bitrate_bps,
                channels=first_info.channels,
                codec=first_info.codec,
                duration_seconds=duration,
                chapter_count=len(track_infos),
                metadata=dict(plan_result.metadata_summary),
                audio_duration_seconds=duration,
                format_duration_seconds=duration,
                duration_source="folder-track-sum",
                stream_summary=tuple(
                    f"{info.path.name}: duration={info.duration_seconds} codec={info.codec}"
                    for info in track_infos
                ),
            ),
            track_infos,
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


def _remove_sidecars(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_folder_sidecars(
    plan: ConversionPlanResult,
    track_infos: tuple[AudioInfo, ...],
    temp_dir: Path,
    metadata: dict[str, str],
) -> tuple[Path, Path]:
    base_name = plan.temporary_output_path.stem if plan.temporary_output_path else plan.source_path.name
    concat_file = temp_dir / f"{base_name}.concat.txt"
    metadata_file = temp_dir / f"{base_name}.ffmetadata.txt"
    concat_file.write_text(
        "".join(f"file '{_ffconcat_escape(path)}'\n" for path in plan.input_paths),
        encoding="utf-8",
    )
    metadata_file.write_text(
        _ffmetadata_text(plan, track_infos, metadata),
        encoding="utf-8",
    )
    return concat_file, metadata_file


def _ffconcat_escape(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace("'", "'\\''")


def _ffmetadata_text(
    plan: ConversionPlanResult,
    track_infos: tuple[AudioInfo, ...],
    metadata: dict[str, str],
) -> str:
    lines = [";FFMETADATA1"]
    for key, value in metadata.items():
        if value:
            lines.append(f"{_ffmetadata_escape(str(key))}={_ffmetadata_escape(str(value))}")
    elapsed_ms = 0
    for index, info in enumerate(track_infos):
        duration_ms = max(1, round(info.duration_seconds * 1000))
        title = plan.chapter_titles[index] if index < len(plan.chapter_titles) else plan.input_paths[index].stem
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={elapsed_ms}",
                f"END={elapsed_ms + duration_ms}",
                f"title={_ffmetadata_escape(title)}",
            ]
        )
        elapsed_ms += duration_ms
    return "\n".join(lines) + "\n"


def _ffmetadata_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace(";", "\\;")
        .replace("#", "\\#")
        .replace("\n", "\\n")
    )
