"""Target selection helpers for conversion queue UI."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Iterable

from .conversion_adapter import VALID_TARGET_BITRATES, VALID_TARGET_CHANNELS
from .conversion_queue import ConversionQueueItem, QueueStatus
from .models import AudioFileMetadata, Book

DRAMATIC_AUDIO_MARKERS = (
    "dramatic audio",
    "dramaticaudio",
    "graphic audio",
    "graphicaudio",
    "dramatic",
    "graphic",
)


@dataclass(frozen=True)
class TargetGuess:
    target_bitrate: int | None
    target_channels: int | None
    reason: str


@dataclass(frozen=True)
class QueueBookTargetState:
    book: Book
    detected_bitrate: int | None
    detected_channels: int | None
    target_bitrate: int | None
    target_channels: int | None
    reason: str

    @property
    def detected_label(self) -> str:
        bitrate = f"{self.detected_bitrate} kbps" if self.detected_bitrate else "Unknown"
        channels = f"{self.detected_channels} ch" if self.detected_channels else "Unknown"
        return f"{bitrate} / {channels}"


def detects_dramatic_audio(book: Book) -> bool:
    for file_meta in book.files:
        if getattr(file_meta, "dramatic_audio", None) is True:
            return True
        values = (
            getattr(file_meta, "album", None),
            getattr(file_meta, "title", None),
            getattr(file_meta, "subtitle", None),
            getattr(file_meta, "author", None),
            getattr(file_meta, "narrator", None),
        )
        text = " ".join(str(value).casefold() for value in values if value)
        if any(marker in text for marker in DRAMATIC_AUDIO_MARKERS):
            return True
    return False


def guess_targets(
    source_bitrate: int | None,
    source_channels: int | None,
    *,
    dramatic_audio: bool,
) -> TargetGuess:
    if source_bitrate is None or source_bitrate <= 0:
        return TargetGuess(None, None, "Missing source bitrate")
    if source_channels is None or source_channels <= 0:
        return TargetGuess(None, None, "Missing source channels")
    if dramatic_audio:
        target = 128 if source_bitrate >= 128 else 64
        return TargetGuess(target, 2, "Detected dramatic audio")
    if source_channels >= 2:
        target = _nearest_valid_bitrate(max(32, source_bitrate / 2))
        return TargetGuess(target, 1, f"Stereo source -> {target} kbps mono")
    target = 64 if source_bitrate >= 60 else 48 if source_bitrate >= 48 else 32
    return TargetGuess(target, 1, f"Mono source -> {target} kbps mono")


def build_target_state(
    book: Book,
    *,
    bitrate_reader: Callable[[AudioFileMetadata], int | None],
    channel_reader: Callable[[AudioFileMetadata], int | None],
) -> QueueBookTargetState:
    detected_bitrate = _first_detected(book.files, bitrate_reader)
    detected_channels = _first_detected(book.files, channel_reader)
    target_bitrate = _common_value(
        (getattr(file_meta, "target_bitrate", None) for file_meta in book.files),
        VALID_TARGET_BITRATES,
    )
    target_channels = _common_value(
        (getattr(file_meta, "target_channels", None) for file_meta in book.files),
        VALID_TARGET_CHANNELS,
    )
    reason = "Manual target" if target_bitrate is not None and target_channels is not None else "No target selected"
    return QueueBookTargetState(
        book=book,
        detected_bitrate=detected_bitrate,
        detected_channels=detected_channels,
        target_bitrate=target_bitrate,
        target_channels=target_channels,
        reason=reason,
    )


def clone_book_with_targets(
    book: Book,
    target_bitrate: int | None,
    target_channels: int | None,
) -> Book:
    files = [
        replace(
            file_meta,
            target_bitrate=target_bitrate,
            target_channels=target_channels,
        )
        for file_meta in book.files
    ]
    return Book(book.key, book.path, book.is_folder_book, files)


def apply_manual_targets(
    state: QueueBookTargetState,
    target_bitrate: int | None,
    target_channels: int | None,
) -> QueueBookTargetState:
    return replace(
        state,
        target_bitrate=target_bitrate,
        target_channels=target_channels,
        reason="Manual target" if target_bitrate is not None and target_channels is not None else "No target selected",
    )


def apply_guessed_targets(state: QueueBookTargetState) -> QueueBookTargetState:
    guess = guess_targets(
        state.detected_bitrate,
        state.detected_channels,
        dramatic_audio=detects_dramatic_audio(state.book),
    )
    return replace(
        state,
        target_bitrate=guess.target_bitrate,
        target_channels=guess.target_channels,
        reason=guess.reason,
    )


def queue_item_dropdown_options(items: Iterable[ConversionQueueItem]) -> list[tuple[str, str]]:
    return [(item.queue_id, item.display_title) for item in items]


def format_queue_target(item: ConversionQueueItem) -> str:
    bitrate = None
    channels = None
    request = getattr(item, "request", None)
    if request is not None:
        bitrate = getattr(request, "target_bitrate", None)
        channels = getattr(request, "target_channels", None)
    prepared = getattr(item, "prepared", None)
    plan = getattr(prepared, "plan", None)
    if bitrate is None and plan is not None:
        bitrate = getattr(plan, "target_bitrate", None)
    if channels is None and plan is not None:
        channels = getattr(plan, "target_channels", None)
    if bitrate is None or channels is None:
        return "Unknown"
    try:
        bitrate_int = int(bitrate)
        channels_int = int(channels)
    except (TypeError, ValueError):
        return "Unknown"
    channel_label = "mono" if channels_int == 1 else "stereo" if channels_int == 2 else str(channels_int)
    return f"{bitrate_int}/{channel_label}"


def queue_status_color_key(status: QueueStatus | str) -> str:
    value = status.value if isinstance(status, QueueStatus) else str(status)
    if value in {"queued", "ready", "planning"}:
        return "light_blue"
    if value in {"converting", "validating", "writing_metadata", "promoting", "archiving"}:
        return "dark_blue"
    if value == "complete":
        return "light_green"
    if value == "failed":
        return "red"
    if value == "cancelled":
        return "gray"
    return "none"


def _nearest_valid_bitrate(value: float) -> int:
    return min(sorted(VALID_TARGET_BITRATES), key=lambda bitrate: (abs(bitrate - value), bitrate))


def _first_detected(
    files: Iterable[AudioFileMetadata],
    reader: Callable[[AudioFileMetadata], int | None],
) -> int | None:
    for file_meta in files:
        value = reader(file_meta)
        if value is not None and value > 0:
            return value
    return None


def _common_value(values: Iterable[object], allowed_values: frozenset[int]) -> int | None:
    normalized = set()
    for value in values:
        if value is None or str(value).strip() == "":
            continue
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        normalized.add(parsed)
    if len(normalized) != 1:
        return None
    value = next(iter(normalized))
    return value if value in allowed_values else None
