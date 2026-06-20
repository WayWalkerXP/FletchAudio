from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil

from .audio_scan import scan_directory
from .models import Book

LOGGER = logging.getLogger(__name__)


@dataclass
class StagingCandidate:
    source_path: Path
    display_name: str
    item_type: str  # "file" or "folder"
    target_bitrate: str
    target_channels: str
    selected: bool = True


@dataclass
class MoveResult:
    source_path: Path
    destination_path: Path
    status: str  # "moved", "skipped", "failed"
    message: str = ""


def _present(value) -> bool:
    return value is not None and str(value).strip() != ""


def candidates_from_books(books: list[Book]) -> list[StagingCandidate]:
    candidates: list[StagingCandidate] = []
    for book in books:
        if not book.files:
            continue
        if book.is_folder_book:
            if not all(_present(file.target_bitrate) and _present(file.target_channels) for file in book.files):
                continue
            bitrate_values = {str(file.target_bitrate).strip() for file in book.files}
            channel_values = {str(file.target_channels).strip() for file in book.files}
            if len(bitrate_values) == 1 and len(channel_values) == 1:
                candidates.append(StagingCandidate(Path(book.path), book.display_name, "folder", next(iter(bitrate_values)), next(iter(channel_values))))
        else:
            file = book.files[0]
            if _present(file.target_bitrate) and _present(file.target_channels):
                candidates.append(StagingCandidate(Path(file.path), book.display_name, "file", str(file.target_bitrate).strip(), str(file.target_channels).strip()))
    LOGGER.info("Found %s staging candidate books", len(candidates))
    return candidates


def discover_staging_candidates(working_dir: Path) -> list[StagingCandidate]:
    books, errors = scan_directory(str(working_dir))
    for error in errors:
        LOGGER.warning("Staging candidate scan warning: %s", error)
    return candidates_from_books(books)


def validate_staging_dir(staging_dir: Path) -> tuple[bool, str]:
    if not staging_dir.exists():
        return False, f"Staging directory does not exist: {staging_dir}"
    if not staging_dir.is_dir():
        return False, f"Staging path is not a directory: {staging_dir}"
    if not os.access(staging_dir, os.W_OK):
        return False, f"Staging directory is not writable: {staging_dir}"
    return True, ""


def destination_for(candidate: StagingCandidate, staging_dir: Path) -> Path:
    return staging_dir / candidate.source_path.name


def move_to_staging(candidate: StagingCandidate, staging_dir: Path) -> MoveResult:
    destination = destination_for(candidate, staging_dir)
    LOGGER.info("Moving staging item %s to %s", candidate.source_path, destination)
    if destination.exists():
        message = f"Skipped {candidate.display_name} because staging destination already exists."
        LOGGER.warning(message)
        return MoveResult(candidate.source_path, destination, "skipped", message)
    try:
        shutil.move(str(candidate.source_path), str(destination))
        message = f"Moved {candidate.display_name} to staging."
        LOGGER.info(message)
        return MoveResult(candidate.source_path, destination, "moved", message)
    except Exception as exc:
        message = f"Failed to move {candidate.display_name}: {exc}"
        LOGGER.exception(message)
        return MoveResult(candidate.source_path, destination, "failed", message)


def verify_copy(source: Path, destination: Path) -> bool:
    if source.is_file():
        return destination.is_file() and source.stat().st_size == destination.stat().st_size
    if not source.is_dir() or not destination.is_dir():
        return False
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        destination_file = destination / relative
        if not destination_file.is_file() or source_file.stat().st_size != destination_file.stat().st_size:
            return False
    return True


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def safe_move_to_staging(candidate: StagingCandidate, staging_dir: Path) -> MoveResult:
    destination = destination_for(candidate, staging_dir)
    LOGGER.info("Safe moving staging item %s to %s", candidate.source_path, destination)
    if destination.exists():
        message = f"Skipped {candidate.display_name} because staging destination already exists."
        LOGGER.warning(message)
        return MoveResult(candidate.source_path, destination, "skipped", message)
    try:
        if candidate.source_path.is_dir():
            shutil.copytree(candidate.source_path, destination)
        else:
            shutil.copy2(candidate.source_path, destination)
    except Exception as exc:
        message = f"Failed to copy {candidate.display_name}: {exc}"
        LOGGER.exception(message)
        return MoveResult(candidate.source_path, destination, "failed", message)
    try:
        if not verify_copy(candidate.source_path, destination):
            _delete_path(destination)
            message = f"Failed to verify copied staging item for {candidate.display_name}; original was kept."
            LOGGER.warning(message)
            return MoveResult(candidate.source_path, destination, "failed", message)
    except Exception as exc:
        if destination.exists():
            _delete_path(destination)
        message = f"Failed to verify {candidate.display_name}: {exc}"
        LOGGER.exception(message)
        return MoveResult(candidate.source_path, destination, "failed", message)
    try:
        _delete_path(candidate.source_path)
        message = f"Safely moved {candidate.display_name} to staging."
        LOGGER.info(message)
        return MoveResult(candidate.source_path, destination, "moved", message)
    except Exception as exc:
        message = f"Copied and verified {candidate.display_name}, but failed to delete original: {exc}"
        LOGGER.exception(message)
        return MoveResult(candidate.source_path, destination, "failed", message)
