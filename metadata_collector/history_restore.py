from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audio_tags import NON_WRITABLE_FIELDS, BOOLEAN_FIELDS, format_genres_for_tag, read_audio_metadata, write_audio_metadata
from .history import create_change_group, log_changes
from .manual_edit import normalize_boolean_value
from .models import ChangeGroup, MetadataChange, AudioFileMetadata

RESTORE_SOURCE_TYPE = 'restore'
RESTORE_DISABLED_TAGS = set(NON_WRITABLE_FIELDS) | {'cover', 'cover_url', 'cover_path', 'delete_cover', 'artwork', 'cover_data', 'cover_data_uri'}


@dataclass
class HistoryChangeGroup:
    group: ChangeGroup
    changed_field_count: int


def list_change_groups_for_file(session, book_key: str, file_path: str) -> list[HistoryChangeGroup]:
    groups = (
        session.query(ChangeGroup)
        .filter(ChangeGroup.book_key == book_key)
        .join(MetadataChange, MetadataChange.change_group_id == ChangeGroup.id)
        .filter(MetadataChange.file_path == file_path)
        .order_by(ChangeGroup.created_at.desc(), ChangeGroup.id.desc())
        .all()
    )
    out: list[HistoryChangeGroup] = []
    for group in groups:
        count = sum(1 for change in group.changes if change.file_path == file_path)
        out.append(HistoryChangeGroup(group=group, changed_field_count=count))
    return out


def changes_for_group_file(session, group_id: int, file_path: str) -> list[MetadataChange]:
    return (
        session.query(MetadataChange)
        .filter(MetadataChange.change_group_id == group_id, MetadataChange.file_path == file_path)
        .order_by(MetadataChange.tag_name.asc())
        .all()
    )


def is_restore_supported(tag: str) -> bool:
    return tag not in RESTORE_DISABLED_TAGS


def normalize_restore_value(tag: str, value: Any) -> Any:
    if tag == 'genres':
        return format_genres_for_tag(value) or ''
    if tag in BOOLEAN_FIELDS:
        return normalize_boolean_value(value)
    if value is None:
        return ''
    return value


def current_value_for_tag(meta: AudioFileMetadata, tag: str) -> Any:
    if tag == 'genres':
        return format_genres_for_tag(meta.genres) or ''
    value = getattr(meta, tag, None)
    if tag in BOOLEAN_FIELDS:
        return normalize_boolean_value(value)
    return '' if value is None else value


def build_restore_updates(meta: AudioFileMetadata, selected_changes: list[MetadataChange]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for change in selected_changes:
        tag = change.tag_name
        if not is_restore_supported(tag) or not hasattr(meta, tag):
            continue
        updates[tag] = normalize_restore_value(tag, change.old_value)
    return updates


def restore_selected_metadata(session, book_key: str, meta: AudioFileMetadata, selected_changes: list[MetadataChange]) -> tuple[ChangeGroup | None, dict[str, tuple[Any, Any]]]:
    updates = build_restore_updates(meta, selected_changes)
    changes = {
        tag: (current_value_for_tag(meta, tag), new_value)
        for tag, new_value in updates.items()
        if current_value_for_tag(meta, tag) != new_value
    }
    if not changes:
        return None, {}
    group = create_change_group(session, book_key, RESTORE_SOURCE_TYPE, 'Metadata restore')
    try:
        write_audio_metadata(meta.path, {tag: new for tag, (_, new) in changes.items()})
    except Exception as exc:
        log_changes(session, group, book_key, meta.path, changes, RESTORE_SOURCE_TYPE, status='failed', error_message=str(exc))
        session.commit()
        raise
    refreshed = read_audio_metadata(meta.path)
    meta.__dict__.update(refreshed.__dict__)
    log_changes(session, group, book_key, meta.path, changes, RESTORE_SOURCE_TYPE)
    session.commit()
    return group, changes
