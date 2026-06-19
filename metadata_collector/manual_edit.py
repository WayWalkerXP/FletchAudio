from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag
from .models import AudioFileMetadata

MANUAL_EDIT_SOURCE_TYPE = 'manual_edit'
BOOLEAN_FIELDS = {'explicit', 'dramatic_audio'}

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


def normalize_manual_value(field: str, value: Any) -> Any:
    if value is None:
        return ''
    if field == 'asin':
        return str(value).strip().upper()
    if field == 'genres':
        return format_genres_for_tag(value) or ''
    if field == 'published_year':
        text = str(value).strip()
        if text and not re.fullmatch(r'\d{4}', text):
            raise ValueError('Published year must be four digits.')
        return text
    if field in {'track', 'disc'}:
        return str(value).strip()
    if field in BOOLEAN_FIELDS:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {'true', 'yes', '1', 'on'}:
            return True
        if text in {'false', 'no', '0', 'off'}:
            return False
        return '' if text == '' else value
    if isinstance(value, str):
        return value.strip() if field in {'published_date', 'language'} else value
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
        if field in BOOLEAN_FIELDS:
            current_value = getattr(current, field, None)
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
    filename = meta.path.rsplit('/', 1)[-1]
    return f'{meta.track}. {filename}' if meta.track is not None else filename


def has_manual_unsaved_changes(current: AudioFileMetadata, edited: dict[str, Any], cover_state: CoverEditState | None = None) -> bool:
    return bool(build_manual_metadata_diff(current, edited, cover_state))


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
