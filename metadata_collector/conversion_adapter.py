"""FletchAudio-native conversion adapter models.

This module intentionally sits between the scanned FletchAudio ``Book`` model and
ported Alchemist engine types.  It only prepares immutable request data for later
conversion planning/execution; it does not plan conversions or run FFmpeg.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import AudioFileMetadata, Book

VALID_TARGET_BITRATES = frozenset({32, 48, 64, 96, 128, 256, 384})
VALID_TARGET_CHANNELS = frozenset({1, 2})
_UNSET_STRINGS = {"", "unset", "none", "null"}


@dataclass(frozen=True)
class ConversionSettings:
    output_dir: Path
    processed_dir: Path | None = None
    temp_dir: Path | None = None
    preferred_codec: str = "libfdk_aac"
    fallback_codec: str = "aac"
    max_bitrate_kbps: int = 384
    extract_cover: bool = True
    archive_original: bool = True
    dry_run: bool = False


@dataclass(frozen=True)
class ConversionRequest:
    book_key: str
    source_path: Path
    is_folder_book: bool
    files: tuple[Path, ...]
    target_bitrate: int | None
    target_channels: int | None
    dramatic_audio: bool | None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversionResult:
    book_key: str
    status: str
    output_path: Path | None
    message: str
    original_bytes: int = 0
    output_bytes: int = 0


class ConversionRequestError(ValueError):
    """Raised when a scanned book cannot be adapted into a conversion request."""


def build_conversion_request(book: Book) -> ConversionRequest:
    """Build an immutable conversion-facing request from a scanned FletchAudio book.

    The returned request contains copied primitive/path data only.  The input
    ``Book`` and its ``AudioFileMetadata`` objects are never modified.
    """
    if not getattr(book, "key", None):
        raise ConversionRequestError("book key is required")
    if not getattr(book, "path", None):
        raise ConversionRequestError("book source path is required")
    if not getattr(book, "files", None):
        raise ConversionRequestError("at least one source audio file is required")

    files = tuple(_path_for(file_meta.path, "file path") for file_meta in book.files)
    target_bitrate = _common_normalized_value(book, "target_bitrate", VALID_TARGET_BITRATES, "target bitrate")
    target_channels = _common_normalized_value(book, "target_channels", VALID_TARGET_CHANNELS, "target channels")
    dramatic_audio = _common_dramatic_audio(book)
    metadata = _collect_metadata(book.files[0])

    return ConversionRequest(
        book_key=str(book.key),
        source_path=_path_for(book.path, "book source path"),
        is_folder_book=bool(book.is_folder_book),
        files=files,
        target_bitrate=target_bitrate,
        target_channels=target_channels,
        dramatic_audio=dramatic_audio,
        metadata=metadata,
    )


def _path_for(value: Any, label: str) -> Path:
    if value is None or str(value) == "":
        raise ConversionRequestError(f"{label} is required")
    return Path(str(value))


def _normalize_optional_int(value: Any, valid_values: frozenset[int], label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in _UNSET_STRINGS:
        return None
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ConversionRequestError(f"invalid {label}: {value!r}") from exc
    if normalized not in valid_values:
        valid = ", ".join(str(item) for item in sorted(valid_values))
        raise ConversionRequestError(f"invalid {label}: {normalized}; expected one of {valid}")
    return normalized


def _common_normalized_value(book: Book, attr: str, valid_values: frozenset[int], label: str) -> int | None:
    values = tuple(_normalize_optional_int(getattr(file_meta, attr, None), valid_values, label) for file_meta in book.files)
    present_values = {value for value in values if value is not None}
    if len(present_values) > 1:
        raise ConversionRequestError(f"inconsistent {label} values across folder book")
    return next(iter(present_values), None)


def _common_dramatic_audio(book: Book) -> bool | None:
    values = {getattr(file_meta, "dramatic_audio", None) for file_meta in book.files if getattr(file_meta, "dramatic_audio", None) is not None}
    if len(values) > 1:
        raise ConversionRequestError("inconsistent dramatic_audio values across folder book")
    return next(iter(values), None)


def _collect_metadata(file_meta: AudioFileMetadata) -> dict[str, str]:
    fields = (
        "title", "album", "author", "albumartist", "narrator", "series",
        "series_sequence", "asin", "description", "publisher",
        "published_year", "published_date", "language",
    )
    metadata: dict[str, str] = {}
    for field_name in fields:
        value = getattr(file_meta, field_name, None)
        if value is not None and str(value) != "":
            metadata[field_name] = str(value)
    if getattr(file_meta, "genres", None):
        metadata["genres"] = ", ".join(str(genre) for genre in file_meta.genres)
    explicit = getattr(file_meta, "explicit", None)
    if explicit is not None:
        metadata["explicit"] = "true" if explicit else "false"
    return metadata
