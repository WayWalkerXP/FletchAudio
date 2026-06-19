from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag
from .models import AudioFileMetadata

MANUAL_EDIT_SOURCE_TYPE = 'manual_edit'

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
    if field in {'explicit', 'dramatic_audio'}:
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
        if field in {'explicit', 'dramatic_audio'}:
            current_value = getattr(current, field, None)
        if normalized != current_value:
            updates[field] = normalized
    if cover_state:
        if cover_state.delete:
            updates['delete_cover'] = True
        elif cover_state.path:
            updates['cover_path'] = cover_state.path
    return updates


def filter_manual_updates_for_file(book_is_folder: bool, updates: dict[str, Any]) -> dict[str, Any]:
    if not book_is_folder:
        return dict(updates)
    return {k: v for k, v in updates.items() if k in FOLDER_SHARED_FIELDS}
