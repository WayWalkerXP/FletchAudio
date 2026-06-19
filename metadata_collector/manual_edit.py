from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from dataclasses import dataclass
from typing import Any

from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag
from .models import AudioFileMetadata

MANUAL_EDIT_SOURCE_TYPE = 'manual_edit'
BOOLEAN_FIELDS = {'explicit', 'dramatic_audio'}
DEBUG_SELECTED_FILE_PATH = ''


def set_debug_dirty_selected_file_path(path: str | None) -> None:
    global DEBUG_SELECTED_FILE_PATH
    DEBUG_SELECTED_FILE_PATH = path or ''


MANUAL_EDIT_TAGS = [
    ('title', 'Title'),
    ('subtitle', 'Subtitle'),
    ('album', 'Album'),
    ('author', 'Author'),
    ('albumartist', 'Album Artist'),
    ('narrator', 'Narrator'),
    ('series', 'Series'),
    ('series_sequence', 'Series Sequence'),
    ('asin', 'ASIN'),
    ('description', 'Description'),
    ('publisher', 'Publisher'),
    ('published_date', 'Published Date'),
    ('published_year', 'Published Year'),
    ('language', 'Language'),
    ('genres', 'Genres'),
    ('explicit', 'Explicit'),
    ('dramatic_audio', 'Dramatic Audio'),
    ('track', 'Track'),
    ('disc', 'Disc'),
    ('cover', 'Cover'),
]

FOLDER_SHARED_FIELDS = {
    'subtitle', 'album', 'author', 'albumartist', 'narrator', 'series', 'series_sequence',
    'asin', 'description', 'publisher', 'published_date', 'published_year', 'language',
    'genres', 'explicit', 'dramatic_audio', 'cover_path', 'delete_cover',
}


@dataclass
class CoverEditState:
    path: str | None = None
    delete: bool = False


def manual_current_value(meta: AudioFileMetadata, field: str) -> Any:
    if field == 'genres':
        return format_genres_for_tag(meta.genres) or ''
    if field == 'cover':
        return meta.cover_data_uri
    value = getattr(meta, field, None)
    if value is None:
        return ''
    return value


def normalize_boolean_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {'', 'false', '0', 'no', 'n', 'off', 'unchecked'}:
        return False
    if text in {'true', '1', 'yes', 'y', 'on', 'checked'}:
        return True
    return bool(value)


def normalize_manual_value(field: str, value: Any) -> Any:
    if field in BOOLEAN_FIELDS:
        return normalize_boolean_value(value)
    if value is None:
        return ''
    if field == 'asin':
        return str(value).strip().upper()
    if field == 'genres':
        return format_genres_for_tag(value) or ''
    if field == 'description':
        return str(value).replace('\r\n', '\n').replace('\r', '\n').strip()
    if field == 'published_year':
        text = str(value).strip()
        if text and not re.fullmatch(r'\d{4}', text):
            raise ValueError('Published year must be four digits.')
        return text
    if field in {'track', 'disc'}:
        return str(value).strip()
    if isinstance(value, str):
        return value.strip()
    return value


def build_manual_metadata_diff(current: AudioFileMetadata, edited: dict[str, Any], cover_state: CoverEditState | None = None) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for field, value in edited.items():
        if field in NON_WRITABLE_FIELDS or field == 'cover':
            continue
        if not hasattr(current, field):
            continue
        normalized = normalize_manual_value(field, value)
        current_value = manual_current_value(current, field)
        current_value = normalize_manual_value(field, current_value)
        if normalized != current_value:
            updates[field] = normalized
    if cover_state:
        if cover_state.delete:
            updates['delete_cover'] = True
        elif cover_state.path:
            updates['cover_path'] = cover_state.path
    return updates



def manual_edit_file_sort_key(meta: AudioFileMetadata) -> tuple[int, int, str]:
    filename = meta.path.rsplit('/', 1)[-1].lower()
    if meta.track is None:
        return (1, 0, filename)
    return (0, int(meta.track), filename)


def sorted_manual_edit_files(files: list[AudioFileMetadata]) -> list[AudioFileMetadata]:
    return sorted(files, key=manual_edit_file_sort_key)


def manual_edit_file_label(meta: AudioFileMetadata) -> str:
    filename = Path(meta.path).name
    if '\\' in filename:
        filename = PureWindowsPath(meta.path).name
    return f'{meta.track}. {filename}' if meta.track is not None else filename


def build_baseline_values(file_metadata: AudioFileMetadata) -> dict[str, Any]:
    return normalize_edit_values({field: manual_current_value(file_metadata, field) for field, _ in MANUAL_EDIT_TAGS if field != 'cover'})


def build_current_metadata_values(file_metadata: AudioFileMetadata) -> dict[str, Any]:
    return build_baseline_values(file_metadata)


def build_edit_form_values(values: dict[str, Any]) -> dict[str, Any]:
    return dict(values)


def normalize_edit_values(values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field, value in values.items():
        if field in NON_WRITABLE_FIELDS or field == 'cover':
            continue
        normalized[field] = normalize_manual_value(field, value)
    return normalized


def normalize_for_dirty_check(values: dict[str, Any]) -> dict[str, Any]:
    return normalize_edit_values(values)


def debug_dirty_check(baseline: dict[str, Any], edited: dict[str, Any]) -> None:
    baseline_normalized = normalize_edit_values(baseline)
    edited_normalized = normalize_edit_values(edited)
    baseline_keys = set(baseline_normalized)
    edited_keys = set(edited_normalized)
    only_baseline = baseline_keys - edited_keys
    only_edited = edited_keys - baseline_keys
    changed_fields = [field for field in sorted(baseline_keys | edited_keys) if baseline_normalized.get(field, normalized_default_value(field)) != edited_normalized.get(field, normalized_default_value(field))]

    print('DIRTY CHECK DEBUG')
    print(f'selected_file_path={DEBUG_SELECTED_FILE_PATH}')
    print()
    print(f'baseline keys: {sorted(baseline_keys)!r}')
    print(f'edited keys: {sorted(edited_keys)!r}')
    print()
    print('Only in baseline:')
    print(f'  {only_baseline!r}')
    print()
    print('Only in edited:')
    print(f'  {only_edited!r}')
    print()
    print('Changed fields:')
    if not changed_fields:
        print('  No dirty fields detected.')
        return
    for field in changed_fields:
        baseline_value = baseline_normalized.get(field, normalized_default_value(field))
        edited_value = edited_normalized.get(field, normalized_default_value(field))
        print(f'  {field}:')
        print(f'    baseline={baseline_value!r} {type(baseline_value)!r}')
        print(f'    edited={edited_value!r} {type(edited_value)!r}')
        print()


def normalized_default_value(field: str) -> Any:
    return False if field in BOOLEAN_FIELDS else ''


def changed_edit_fields(baseline: dict[str, Any], edited: dict[str, Any], cover_state: CoverEditState | None = None) -> dict[str, tuple[Any, Any]]:
    baseline_normalized = normalize_edit_values(baseline)
    edited_normalized = normalize_edit_values(build_edit_form_values(edited))
    changed = {
        field: (baseline_normalized.get(field, normalized_default_value(field)), edited_normalized.get(field, normalized_default_value(field)))
        for field in sorted(set(baseline_normalized) | set(edited_normalized))
        if baseline_normalized.get(field, normalized_default_value(field)) != edited_normalized.get(field, normalized_default_value(field))
    }
    if cover_state and cover_state.delete:
        changed['delete_cover'] = (False, True)
    elif cover_state and cover_state.path:
        changed['cover_path'] = ('', cover_state.path)
    return changed


def has_unsaved_changes(baseline: dict[str, Any], edited: dict[str, Any], cover_state: CoverEditState | None = None) -> bool:
    changed = changed_edit_fields(baseline, edited, cover_state)
    if changed:
        debug_dirty_check(baseline, edited)
    return bool(changed)


def manual_changed_fields(current: AudioFileMetadata, edited: dict[str, Any], cover_state: CoverEditState | None = None) -> dict[str, tuple[Any, Any]]:
    return changed_edit_fields(build_baseline_values(current), edited, cover_state)


def has_manual_unsaved_changes(current: AudioFileMetadata, edited: dict[str, Any], cover_state: CoverEditState | None = None) -> bool:
    return bool(manual_changed_fields(current, edited, cover_state))


def should_switch_manual_file(has_unsaved_changes: bool, decision: str | None) -> tuple[bool, bool]:
    if not has_unsaved_changes:
        return (True, False)
    if decision == 'save':
        return (True, True)
    if decision == 'discard':
        return (True, False)
    return (False, False)


def filter_manual_updates_for_file(book_is_folder: bool, updates: dict[str, Any]) -> dict[str, Any]:
    if not book_is_folder:
        return dict(updates)
    return {k: v for k, v in updates.items() if k in FOLDER_SHARED_FIELDS}
