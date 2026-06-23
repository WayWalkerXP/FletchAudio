"""Read-only conversion planning for FletchAudio conversion requests."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Literal

from .alchemist_engine.filesystem import sanitize_filename
from .alchemist_engine.metadata import build_output_tags, first_tag_value
from .conversion_adapter import (
    VALID_TARGET_BITRATES,
    VALID_TARGET_CHANNELS,
    ConversionRequest,
    ConversionSettings,
)

PlanStatus = Literal["planned", "skipped", "invalid"]


@dataclass(frozen=True)
class ConversionPlanResult:
    """Structured preview of one conversion, including validation diagnostics."""

    book_key: str
    source_path: Path
    input_paths: tuple[Path, ...]
    is_folder_book: bool
    output_path: Path | None
    temporary_output_path: Path | None
    archive_path: Path | None
    target_bitrate: int | None
    target_channels: int | None
    selected_codec: str | None
    dramatic_audio_output: bool
    metadata_summary: dict[str, str]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    status: PlanStatus


class ConversionPlanner:
    """Build deterministic conversion previews without executing or writing."""

    def __init__(self, settings: ConversionSettings) -> None:
        self.settings = settings

    def plan(self, request: ConversionRequest) -> ConversionPlanResult:
        warnings: list[str] = []
        errors: list[str] = []

        self._validate_paths(request, errors)
        self._validate_targets(request, errors)

        metadata = {
            str(key): str(value).strip()
            for key, value in request.metadata.items()
            if value is not None and str(value).strip()
        }
        author = first_tag_value(
            metadata,
            ("author", "artist", "albumartist", "album_artist", "composer"),
        )
        album = first_tag_value(metadata, ("album", "title"))
        if not author:
            errors.append("author metadata is required to build the output filename")
        if not album:
            errors.append("album or title metadata is required to build the output filename")

        output_path: Path | None = None
        temporary_path: Path | None = None
        archive_path: Path | None = None
        if author and album and self._output_directory_is_usable():
            safe_author = sanitize_filename(author)
            safe_album = sanitize_filename(album)
            if safe_author == "Untitled":
                errors.append("author metadata does not contain a usable filename component")
            if safe_album == "Untitled":
                errors.append("album metadata does not contain a usable filename component")
            if safe_author != "Untitled" and safe_album != "Untitled":
                output_path = self.settings.output_dir / f"{safe_author} - {safe_album}.m4b"
                temp_dir = self.settings.temp_dir or self.settings.output_dir
                temporary_path = temp_dir / f"{safe_author} - {safe_album}.tmp.m4b"

        if self.settings.archive_original and self.settings.processed_dir is not None:
            archive_path = self.settings.processed_dir / request.source_path.name

        self._detect_conflicts(
            request,
            output_path,
            temporary_path,
            archive_path,
            warnings,
            errors,
        )
        if request.is_folder_book and not _has_certain_track_order(request.files):
            warnings.append(
                "folder track order is preserved from the request, but filename-based ordering is uncertain"
            )

        metadata_summary = (
            build_output_tags(
                metadata,
                fallback_author=author,
                fallback_album=album,
                dramatic_audio=request.dramatic_audio is True,
            )
            if author and album
            else metadata
        )
        return ConversionPlanResult(
            book_key=request.book_key,
            source_path=request.source_path,
            input_paths=request.files,
            is_folder_book=request.is_folder_book,
            output_path=output_path,
            temporary_output_path=temporary_path,
            archive_path=archive_path,
            target_bitrate=request.target_bitrate,
            target_channels=request.target_channels,
            selected_codec=self.settings.preferred_codec or self.settings.fallback_codec or None,
            dramatic_audio_output=request.dramatic_audio is True,
            metadata_summary=metadata_summary,
            warnings=tuple(warnings),
            errors=tuple(errors),
            status="invalid" if errors else "planned",
        )

    def plan_many(
        self, requests: Iterable[ConversionRequest]
    ) -> list[ConversionPlanResult]:
        results = [self.plan(request) for request in requests]
        output_indexes: dict[Path, list[int]] = {}
        for index, result in enumerate(results):
            if result.output_path is not None:
                output_indexes.setdefault(result.output_path, []).append(index)

        for output_path, indexes in output_indexes.items():
            if len(indexes) < 2:
                continue
            message = f"multiple requests target the same output path: {output_path}"
            for index in indexes:
                result = results[index]
                results[index] = replace(
                    result,
                    errors=(*result.errors, message),
                    status="invalid",
                )
        return results

    def _validate_paths(
        self, request: ConversionRequest, errors: list[str]
    ) -> None:
        if not request.book_key.strip():
            errors.append("book key is required")
        if not request.source_path.exists():
            if request.is_folder_book:
                errors.append(f"source folder does not exist: {request.source_path}")
            else:
                errors.append(f"Source file does not exist: {request.source_path}")
        elif request.is_folder_book and not request.source_path.is_dir():
            errors.append(f"folder-book source path is not a directory: {request.source_path}")
        elif not request.is_folder_book and not request.source_path.is_file():
            errors.append(f"single-file source path is not a file: {request.source_path}")

        if not request.files:
            errors.append("at least one input file is required")
        for input_path in request.files:
            if not input_path.is_file():
                errors.append(f"input file does not exist: {input_path}")

        self._validate_directory(self.settings.output_dir, "output", errors)
        if self.settings.temp_dir is not None:
            self._validate_directory(self.settings.temp_dir, "temporary output", errors)
        if self.settings.archive_original and self.settings.processed_dir is not None:
            self._validate_archive_directory(self.settings.processed_dir, errors)

    def _validate_targets(
        self, request: ConversionRequest, errors: list[str]
    ) -> None:
        if request.target_bitrate not in VALID_TARGET_BITRATES:
            allowed = ", ".join(str(value) for value in sorted(VALID_TARGET_BITRATES))
            errors.append(f"target bitrate must be one of: {allowed}")
        elif request.target_bitrate > self.settings.max_bitrate_kbps:
            errors.append(
                f"target bitrate exceeds configured maximum of "
                f"{self.settings.max_bitrate_kbps} kbps"
            )
        if request.target_channels not in VALID_TARGET_CHANNELS:
            errors.append("target channels must be 1 or 2")
        if not (self.settings.preferred_codec or self.settings.fallback_codec):
            errors.append("a conversion codec is required")

    @staticmethod
    def _validate_directory(
        path: Path | None, label: str, errors: list[str]
    ) -> None:
        if path is None:
            errors.append(f"{label} directory is required")
        elif not path.exists():
            errors.append(f"{label} directory does not exist: {path}")
        elif not path.is_dir():
            errors.append(f"{label} directory is not a directory: {path}")

    @staticmethod
    def _validate_archive_directory(path: Path, errors: list[str]) -> None:
        if path.exists() and not path.is_dir():
            errors.append(f"archive directory is not a directory: {path}")

    def _output_directory_is_usable(self) -> bool:
        output_dir = self.settings.output_dir
        return output_dir is not None and output_dir.is_dir()

    @staticmethod
    def _detect_conflicts(
        request: ConversionRequest,
        output_path: Path | None,
        temporary_path: Path | None,
        archive_path: Path | None,
        warnings: list[str],
        errors: list[str],
    ) -> None:
        destinations = (
            ("output", output_path),
            ("temporary output", temporary_path),
            ("archive", archive_path),
        )
        source_paths = {request.source_path, *request.files}
        for label, path in destinations:
            if path is None:
                continue
            if path in source_paths:
                errors.append(f"{label} path conflicts with a source path: {path}")
            if path.exists() and label != "archive":
                warnings.append(f"{label} destination already exists: {path}")
                errors.append(f"{label} destination conflict: {path}")


def plan_conversion(
    request: ConversionRequest, settings: ConversionSettings
) -> ConversionPlanResult:
    """Plan one request using explicit conversion settings."""
    return ConversionPlanner(settings).plan(request)


def plan_conversions(
    requests: Iterable[ConversionRequest], settings: ConversionSettings
) -> list[ConversionPlanResult]:
    """Plan requests and report conflicts within the batch."""
    return ConversionPlanner(settings).plan_many(requests)


_LEADING_TRACK_NUMBER = re.compile(r"^\s*(\d+)")


def _has_certain_track_order(paths: tuple[Path, ...]) -> bool:
    if len(paths) < 2:
        return True
    numbers: list[int] = []
    for path in paths:
        match = _LEADING_TRACK_NUMBER.match(path.stem)
        if match is None:
            return False
        numbers.append(int(match.group(1)))
    return len(numbers) == len(set(numbers)) and numbers == sorted(numbers)
