"""Archive helpers for completed audiobook conversions."""
from __future__ import annotations

import shutil
from pathlib import Path


def archive_source_file(source_path: Path, archive_directory: Path) -> Path:
    """Move a converted source file into an archive directory without overwriting."""
    archive_directory.mkdir(parents=True, exist_ok=True)
    if not archive_directory.is_dir():
        raise NotADirectoryError(f"Archive path is not a directory: {archive_directory}")
    destination = _collision_safe_path(archive_directory / source_path.name)
    return Path(shutil.move(str(source_path), str(destination)))


def _collision_safe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
