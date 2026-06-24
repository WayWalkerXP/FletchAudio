from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .models import Book

STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_ERROR = "ERROR"

DUPLICATE_NONE = ""
DUPLICATE_NO_MATCH = "No Duplicate"
DUPLICATE_ASIN = "ASIN Match"
DUPLICATE_AUTHOR_ALBUM = "Author & Album Match"

COLLISION_SKIP = "skip"
COLLISION_OVERWRITE = "overwrite"
COLLISION_SKIP_ALL = "skip_all"
COLLISION_OVERWRITE_ALL = "overwrite_all"


@dataclass
class LibraryMoveItem:
    book: Book
    source_root: Path
    source_kind: str
    status: str
    status_detail: str = ""
    duplicate: str = DUPLICATE_NONE
    selected: bool = False
    checkable: bool = True

    @property
    def metadata(self):
        return self.book.files[0] if self.book.files else None

    @property
    def author(self) -> str:
        return _clean(getattr(self.metadata, "author", None))

    @property
    def album(self) -> str:
        return _clean(getattr(self.metadata, "album", None))

    @property
    def series(self) -> str:
        return _clean(getattr(self.metadata, "series", None))

    @property
    def series_sequence(self) -> str:
        return _clean(getattr(self.metadata, "series_sequence", None))

    @property
    def asin(self) -> str:
        return _clean(getattr(self.metadata, "asin", None))

    @property
    def num_files(self) -> int:
        return len(self.book.files)


@dataclass(frozen=True)
class LibraryMoveTarget:
    item: LibraryMoveItem
    destination_folder: Path
    target_paths: tuple[Path, ...]
    item_type: str


@dataclass(frozen=True)
class DryRunRow:
    item: LibraryMoveItem
    target: LibraryMoveTarget
    target_exists: str


@dataclass
class LibraryMoveReport:
    moved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    overwritten: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    source_folders_deleted: list[str] = field(default_factory=list)
    source_folders_not_deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _clean(value) -> str:
    return str(value or "").strip()


def _safe_segment(value: str) -> str:
    text = _clean(value)
    for char in '<>:"/\\|?*':
        text = text.replace(char, "_")
    return text.rstrip(" .") or "_"


def _source_roots(settings: Mapping[str, object]) -> list[tuple[str, Path]]:
    roots = []
    for key, label in (("staging_dir", "staging"), ("conversion_output_dir", "converted")):
        value = _clean(settings.get(key))
        if value:
            roots.append((label, Path(value).expanduser()))
    return roots


def validate_item(book: Book, source_root: Path, source_kind: str) -> LibraryMoveItem:
    meta = book.files[0] if book.files else None
    missing = []
    if not _clean(getattr(meta, "author", None)):
        missing.append("Author")
    if not _clean(getattr(meta, "album", None)):
        missing.append("Album")
    if missing:
        return LibraryMoveItem(
            book=book,
            source_root=source_root,
            source_kind=source_kind,
            status=STATUS_ERROR,
            status_detail=f"Missing: {', '.join(missing)}",
            selected=False,
            checkable=False,
        )
    return LibraryMoveItem(
        book=book,
        source_root=source_root,
        source_kind=source_kind,
        status=STATUS_OK,
        selected=True,
        checkable=True,
    )


def discover_library_move_items(settings: Mapping[str, object]) -> tuple[list[LibraryMoveItem], list[str]]:
    from .audio_scan import scan_directory

    items: list[LibraryMoveItem] = []
    errors: list[str] = []
    seen: set[str] = set()
    for source_kind, root in _source_roots(settings):
        if not root.exists():
            errors.append(f"{source_kind} folder does not exist: {root}")
            continue
        if not root.is_dir():
            errors.append(f"{source_kind} path is not a folder: {root}")
            continue
        books, scan_errors = scan_directory(str(root))
        errors.extend(scan_errors)
        for book in books:
            resolved = str(Path(book.path).resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            items.append(validate_item(book, root, source_kind))
    return items, errors


def target_for_item(item: LibraryMoveItem, abs_root: Path) -> LibraryMoveTarget:
    author = _safe_segment(item.author)
    album = _safe_segment(item.album)
    series = _safe_segment(item.series) if item.series else ""
    sequence = _safe_segment(item.series_sequence) if item.series_sequence else ""
    if series:
        album_folder = f"{sequence} {album}".strip() if sequence else album
        destination_folder = abs_root / author / series / album_folder
    else:
        destination_folder = abs_root / author / album
    if item.book.is_folder_book:
        targets = tuple(destination_folder / Path(file_meta.path).name for file_meta in item.book.files)
        return LibraryMoveTarget(item=item, destination_folder=destination_folder, target_paths=targets, item_type="Folder")
    return LibraryMoveTarget(
        item=item,
        destination_folder=destination_folder,
        target_paths=(destination_folder / f"{album}.m4b",),
        item_type="File",
    )


def selected_items(items: Iterable[LibraryMoveItem]) -> list[LibraryMoveItem]:
    return [item for item in items if item.selected and item.checkable]


def target_exists_label(target: LibraryMoveTarget) -> str:
    if target.item.book.is_folder_book:
        if target.destination_folder.exists():
            return "Yes - Folder Exists"
        if any(path.exists() for path in target.target_paths):
            return "Yes - One or More Files Exist"
        return "No"
    target_file = target.target_paths[0]
    if target_file.exists():
        return "Yes - File Exists"
    if target_file.parent.exists() and not target_file.parent.is_dir():
        return "Yes - File Exists"
    return "No"


def dry_run(items: Iterable[LibraryMoveItem], abs_root: Path) -> list[DryRunRow]:
    rows = []
    for item in selected_items(items):
        target = target_for_item(item, abs_root)
        rows.append(DryRunRow(item=item, target=target, target_exists=target_exists_label(target)))
    return rows


def apply_duplicate_result(item: LibraryMoveItem, duplicate_display: str) -> None:
    item.duplicate = duplicate_display
    if duplicate_display in {DUPLICATE_ASIN, DUPLICATE_AUTHOR_ALBUM}:
        item.status = STATUS_WARN
        item.status_detail = ""
        item.selected = False
        item.checkable = True
    elif item.status != STATUS_ERROR:
        item.duplicate = DUPLICATE_NO_MATCH


def _unique_backup_path(destination: Path) -> Path:
    candidate = destination.with_name(f"{destination.name}_backup")
    index = 1
    while candidate.exists():
        candidate = destination.with_name(f"{destination.name}_backup_{index}")
        index += 1
    return candidate


def _cleanup_source_folder(item: LibraryMoveItem, report: LibraryMoveReport) -> None:
    if not item.book.is_folder_book:
        return
    source = Path(item.book.path)
    try:
        source.rmdir()
        report.source_folders_deleted.append(str(source))
    except OSError:
        report.source_folders_not_deleted.append(str(source))


def _move_single_file(item: LibraryMoveItem, target: LibraryMoveTarget, overwrite: bool, report: LibraryMoveReport) -> None:
    source = Path(item.book.path)
    destination = target.target_paths[0]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not overwrite:
            report.skipped.append(str(source))
            return
        destination.unlink()
        report.overwritten.append(str(destination))
    shutil.move(str(source), str(destination))
    report.moved.append(str(destination))


def _move_folder_book(item: LibraryMoveItem, target: LibraryMoveTarget, overwrite: bool, report: LibraryMoveReport) -> None:
    source = Path(item.book.path)
    destination = target.destination_folder
    backup = None
    if destination.exists():
        if not overwrite:
            report.skipped.append(str(source))
            return
        backup = _unique_backup_path(destination)
        destination.rename(backup)
        report.overwritten.append(str(destination))
    try:
        destination.mkdir(parents=True, exist_ok=False)
        for file_meta in item.book.files:
            source_file = Path(file_meta.path)
            shutil.move(str(source_file), str(destination / source_file.name))
        if backup:
            shutil.rmtree(backup)
        report.moved.append(str(destination))
        _cleanup_source_folder(item, report)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if backup and backup.exists():
            backup.rename(destination)
            report.errors.append(f"Restored backup after failed overwrite: {destination}")
        raise


def move_items(
    items: Iterable[LibraryMoveItem],
    abs_root: Path,
    collision_decider: Callable[[LibraryMoveItem, LibraryMoveTarget], str] | None = None,
) -> LibraryMoveReport:
    report = LibraryMoveReport()
    collision_policy: str | None = None
    for item in selected_items(items):
        target = target_for_item(item, abs_root)
        exists = target_exists_label(target) != "No"
        overwrite = False
        if exists:
            choice = collision_policy
            if choice is None and collision_decider is not None:
                choice = collision_decider(item, target)
            choice = choice or COLLISION_SKIP
            if choice == COLLISION_SKIP_ALL:
                collision_policy = COLLISION_SKIP
                choice = COLLISION_SKIP
            elif choice == COLLISION_OVERWRITE_ALL:
                collision_policy = COLLISION_OVERWRITE
                choice = COLLISION_OVERWRITE
            if choice == COLLISION_SKIP:
                report.skipped.append(str(item.book.path))
                continue
            overwrite = choice == COLLISION_OVERWRITE
        try:
            if item.book.is_folder_book:
                _move_folder_book(item, target, overwrite, report)
            else:
                _move_single_file(item, target, overwrite, report)
        except Exception as exc:
            report.failed.append(str(item.book.path))
            report.errors.append(f"{item.book.path}: {exc}")
    return report
