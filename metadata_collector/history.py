import base64
import hashlib
import json
import re
from datetime import datetime, timedelta
from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag
from .models import BookSnapshot, ChangeGroup, MetadataChange
from .utils import json_dumps, stringify

_DATA_URI_RE = re.compile(r'^data:(?P<mime>image/[^;]+);base64,(?P<data>.*)$', re.IGNORECASE | re.DOTALL)
_BASE64_RE = re.compile(r'^[A-Za-z0-9+/\s]+={0,2}$')
_COVER_KEYS = {'cover_data_uri', 'cover_data', 'artwork', 'artwork_data', 'image_data', 'cover_bytes', 'cover_blob'}
_COVER_META_KEYS = {'has_cover', 'cover_mime_type', 'cover_size_bytes', 'cover_sha256'}


def _decode_base64_image(value):
    if not isinstance(value, str):
        return None
    match = _DATA_URI_RE.match(value.strip())
    if match:
        try:
            data = base64.b64decode(match.group('data'), validate=False)
        except Exception:
            data = b''
        return match.group('mime'), data
    text = value.strip()
    if len(text) < 512 or len(text) % 4 or not _BASE64_RE.match(text):
        return None
    try:
        data = base64.b64decode(text, validate=True)
    except Exception:
        return None
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg', data
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png', data
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp', data
    return None


def cover_metadata_from_value(value):
    decoded = _decode_base64_image(value)
    if not decoded:
        return {'has_cover': bool(value)} if value not in (None, '', False) else {'has_cover': False}
    mime_type, data = decoded
    meta = {'has_cover': True, 'cover_mime_type': mime_type}
    if data:
        meta['cover_size_bytes'] = len(data)
        meta['cover_sha256'] = hashlib.sha256(data).hexdigest()
    return meta


def sanitize_metadata_json_value(value):
    if isinstance(value, list):
        return [sanitize_metadata_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    sanitized = {}
    cover_meta = {}
    for key, item in value.items():
        if key in _COVER_KEYS:
            cover_meta.update(cover_metadata_from_value(item))
            continue
        if key in _COVER_META_KEYS:
            sanitized[key] = item
            continue
        if isinstance(item, (dict, list)):
            sanitized[key] = sanitize_metadata_json_value(item)
        else:
            sanitized[key] = item
    if 'cover_url' in value and value.get('cover_url') and 'has_cover' not in sanitized and 'has_cover' not in cover_meta:
        cover_meta['has_cover'] = True
    sanitized.update(cover_meta)
    return sanitized


def sanitize_snapshot_payload(files):
    return sanitize_metadata_json_value(files)


def describe_cover_value(value, action='present'):
    meta = cover_metadata_from_value(value)
    if not meta.get('has_cover'):
        return 'missing' if action != 'deleted' else 'deleted'
    digest = meta.get('cover_sha256')
    suffix = f' sha256={digest}' if digest else ''
    if action == 'replaced':
        return f'cover replaced{suffix}'
    return f'cover present{suffix}'


def _stringify_change_value(tag, value, is_new=False):
    if _decode_base64_image(value):
        return describe_cover_value(value, 'replaced' if is_new else 'present')
    if tag in {'cover', 'cover_data_uri', 'cover_data', 'artwork', 'cover_path', 'cover_url', 'delete_cover'}:
        if tag == 'delete_cover' or value is True:
            return 'deleted' if is_new else describe_cover_value(value)
        if tag in {'cover_path', 'cover_url'} and value:
            return 'cover replaced'
        return describe_cover_value(value, 'replaced' if is_new else 'present')
    return stringify(format_genres_for_tag(value) if tag == 'genres' else value)


def store_snapshot(session, book, source_type='scan'):
    payload = sanitize_snapshot_payload([f.to_dict() for f in book.files])
    snap=BookSnapshot(book_key=book.key,path=book.path,is_folder_book=book.is_folder_book,source_type=source_type,metadata_json=json_dumps(payload))
    session.add(snap); session.commit(); return snap


def create_change_group(session, book_key, source_type, description=None):
    group=ChangeGroup(book_key=book_key,source_type=source_type,description=description); session.add(group); session.flush(); return group


def metadata_diff(current, selected):
    normalized_selected = dict(selected)
    if 'genres' in normalized_selected:
        normalized_selected['genres'] = format_genres_for_tag(normalized_selected['genres'])
    return {k:v for k,v in normalized_selected.items() if k not in NON_WRITABLE_FIELDS and v not in (None, []) and (format_genres_for_tag(getattr(current,k,None)) if k == 'genres' else getattr(current,k,None))!=v}


def log_changes(session, group, book_key, file_path, changes, source_type, status='success', error_message=None):
    rows=[]
    for tag,(old,new) in changes.items():
        row=MetadataChange(change_group_id=group.id,book_key=book_key,file_path=file_path,tag_name=tag,old_value=_stringify_change_value(tag, old),new_value=_stringify_change_value(tag, new, True),source_type=source_type,status=status,error_message=error_message)
        session.add(row); rows.append(row)
    session.flush(); return rows


def selectable_restore_values(snapshot: BookSnapshot, selected_tags: list[str], file_path: str|None=None):
    data=json.loads(snapshot.metadata_json)
    if file_path: data=[d for d in data if d.get('path')==file_path]
    out={}
    for item in data:
        out[item['path']]={tag:item.get(tag) for tag in selected_tags if tag in item and tag != 'cover_data_uri'}
    return out


def history_for_book(session, book_key):
    return {'snapshots':session.query(BookSnapshot).filter_by(book_key=book_key).order_by(BookSnapshot.created_at.desc()).all(), 'change_groups':session.query(ChangeGroup).filter_by(book_key=book_key).order_by(ChangeGroup.created_at.desc()).all()}


def cleanup_cover_bloat(session):
    changed = {'snapshots': 0, 'changes': 0}
    for snap in session.query(BookSnapshot).all():
        try:
            original = json.loads(snap.metadata_json)
        except Exception:
            continue
        sanitized = sanitize_metadata_json_value(original)
        new_json = json_dumps(sanitized)
        if new_json != snap.metadata_json:
            snap.metadata_json = new_json
            changed['snapshots'] += 1
    for row in session.query(MetadataChange).all():
        old_value = _stringify_change_value(row.tag_name, row.old_value)
        new_value = _stringify_change_value(row.tag_name, row.new_value, True)
        if old_value != row.old_value or new_value != row.new_value:
            row.old_value = old_value
            row.new_value = new_value
            changed['changes'] += 1
    session.commit()
    return changed


def cleanup_metadata_history(session, days_to_keep=3):
    try:
        days = int(days_to_keep)
    except (TypeError, ValueError):
        days = 3
    cutoff = datetime.utcnow() - timedelta(days=max(days, 0))
    deleted = {'snapshots': 0, 'changes': 0, 'change_groups': 0}
    deleted['snapshots'] = session.query(BookSnapshot).filter(BookSnapshot.created_at < cutoff).delete(synchronize_session=False)
    deleted['changes'] = session.query(MetadataChange).filter(MetadataChange.changed_at < cutoff).delete(synchronize_session=False)
    for group in session.query(ChangeGroup).filter(ChangeGroup.created_at < cutoff).all():
        remaining = session.query(MetadataChange).filter_by(change_group_id=group.id).count()
        if remaining == 0:
            session.delete(group)
            deleted['change_groups'] += 1
    session.commit()
    return deleted
