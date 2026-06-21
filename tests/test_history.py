import json
from metadata_collector.history import cleanup_metadata_history, metadata_diff, selectable_restore_values
from metadata_collector.models import AudioFileMetadata, BookSnapshot

def test_metadata_diff_generation():
    cur=AudioFileMetadata(path='a', title='Old', author='Same')
    assert metadata_diff(cur, {'title':'New','author':'Same','asin':None}) == {'title':'New'}

def test_restore_selection_logic():
    snap=BookSnapshot(book_key='k', path='p', is_folder_book=False, source_type='scan', metadata_json=json.dumps([{'path':'a','title':'Old','author':'A','asin':'X'}]))
    assert selectable_restore_values(snap, ['title','asin'], 'a') == {'a': {'title':'Old','asin':'X'}}


def test_metadata_diff_excludes_non_writable_fields():
    cur=AudioFileMetadata(path='a', title='Old', duration=100, has_cover=False)
    assert metadata_diff(cur, {'title':'New','duration':200,'has_cover':True}) == {'title':'New'}

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from metadata_collector.history import log_changes, create_change_group, sanitize_snapshot_payload
from metadata_collector.models import Base


def test_snapshot_sanitizer_replaces_cover_data_uri_with_metadata():
    payload = sanitize_snapshot_payload([{'path': 'a', 'title': 'Old', 'cover_data_uri': 'data:image/png;base64,iVBORw0KGgo='}])
    assert payload[0]['title'] == 'Old'
    assert 'cover_data_uri' not in payload[0]
    assert payload[0]['has_cover'] is True
    assert payload[0]['cover_mime_type'] == 'image/png'
    assert payload[0]['cover_size_bytes'] == 8
    assert payload[0]['cover_sha256']


def test_log_changes_describes_cover_values_without_base64():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    db_session = Session()
    group = create_change_group(db_session, 'k', 'manual')
    rows = log_changes(db_session, group, 'k', 'a', {'cover_data_uri': ('data:image/png;base64,iVBORw0KGgo=', None)}, 'manual')
    assert rows[0].old_value.startswith('cover present sha256=')
    assert rows[0].new_value == 'missing'
    assert 'base64' not in rows[0].old_value

from datetime import datetime, timedelta
from metadata_collector.history_restore import (
    build_restore_updates,
    is_restore_supported,
    list_change_groups_for_file,
    restore_selected_metadata,
)
from metadata_collector.models import ChangeGroup, MetadataChange


def _memory_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _add_change(session, book_key, file_path, tag, old, new, when):
    group = ChangeGroup(book_key=book_key, source_type='manual', description=f'{tag} change', created_at=when)
    session.add(group)
    session.flush()
    change = MetadataChange(change_group_id=group.id, book_key=book_key, file_path=file_path, tag_name=tag, old_value=old, new_value=new, source_type='manual', changed_at=when)
    session.add(change)
    session.commit()
    return group, change


def _add_snapshot(session, book_key, when):
    snap = BookSnapshot(book_key=book_key, path=f'{book_key}.mp3', is_folder_book=False, source_type='scan', metadata_json='[]', created_at=when)
    session.add(snap)
    session.commit()
    return snap


def test_list_change_groups_newest_first():
    session = _memory_session()
    old, newer = datetime.utcnow() - timedelta(days=1), datetime.utcnow()
    first, _ = _add_change(session, 'book', 'a.mp3', 'title', 'Old', 'New', old)
    second, _ = _add_change(session, 'book', 'a.mp3', 'author', 'A', 'B', newer)
    groups = list_change_groups_for_file(session, 'book', 'a.mp3')
    assert [item.group.id for item in groups] == [second.id, first.id]
    assert [item.changed_field_count for item in groups] == [1, 1]


def test_cleanup_metadata_history_deletes_only_old_history():
    session = _memory_session()
    old = datetime.utcnow() - timedelta(days=5)
    recent = datetime.utcnow()
    old_snapshot = _add_snapshot(session, 'old-book', old)
    recent_snapshot = _add_snapshot(session, 'recent-book', recent)
    old_group, _ = _add_change(session, 'old-book', 'old.mp3', 'title', 'Old', 'New', old)
    recent_group, _ = _add_change(session, 'recent-book', 'recent.mp3', 'title', 'Old', 'New', recent)
    old_snapshot_id = old_snapshot.id
    recent_snapshot_id = recent_snapshot.id
    old_group_id = old_group.id
    recent_group_id = recent_group.id

    deleted = cleanup_metadata_history(session, days_to_keep=3)

    assert deleted == {'snapshots': 1, 'changes': 1, 'change_groups': 1}
    assert session.get(BookSnapshot, old_snapshot_id) is None
    assert session.get(BookSnapshot, recent_snapshot_id) is not None
    assert session.query(MetadataChange).filter_by(book_key='old-book').count() == 0
    assert session.query(MetadataChange).filter_by(book_key='recent-book').count() == 1
    assert session.get(ChangeGroup, old_group_id) is None
    assert session.get(ChangeGroup, recent_group_id) is not None


def test_restore_one_selected_tag_builds_update():
    meta = AudioFileMetadata(path='a.mp3', title='New', author='Same')
    change = MetadataChange(change_group_id=1, book_key='book', file_path='a.mp3', tag_name='title', old_value='Old', new_value='New', source_type='manual')
    assert build_restore_updates(meta, [change]) == {'title': 'Old'}


def test_restore_multiple_selected_tags_normalizes_values():
    meta = AudioFileMetadata(path='a.mp3', title='New', explicit=True, genres=['New'])
    changes = [
        MetadataChange(change_group_id=1, book_key='book', file_path='a.mp3', tag_name='title', old_value='Old', new_value='New', source_type='manual'),
        MetadataChange(change_group_id=1, book_key='book', file_path='a.mp3', tag_name='explicit', old_value='false', new_value='true', source_type='manual'),
        MetadataChange(change_group_id=1, book_key='book', file_path='a.mp3', tag_name='genres', old_value='Fantasy\\Adventure', new_value='New', source_type='manual'),
    ]
    assert build_restore_updates(meta, changes) == {'title': 'Old', 'explicit': False, 'genres': 'Fantasy\\\\Adventure'}


def test_unchecked_tags_are_untouched_by_restore(monkeypatch):
    session = _memory_session()
    _, title_change = _add_change(session, 'book', 'a.mp3', 'title', 'Old', 'New', datetime.utcnow())
    _add_change(session, 'book', 'a.mp3', 'author', 'Old Author', 'New Author', datetime.utcnow())
    meta = AudioFileMetadata(path='a.mp3', title='New', author='New Author')
    written = {}
    monkeypatch.setattr('metadata_collector.history_restore.write_audio_metadata', lambda path, updates: written.update(updates))
    monkeypatch.setattr('metadata_collector.history_restore.read_audio_metadata', lambda path: AudioFileMetadata(path=path, title='Old', author='New Author'))
    restore_selected_metadata(session, 'book', meta, [title_change])
    assert written == {'title': 'Old'}


def test_empty_old_value_restores_correctly():
    meta = AudioFileMetadata(path='a.mp3', title='New')
    change = MetadataChange(change_group_id=1, book_key='book', file_path='a.mp3', tag_name='title', old_value='', new_value='New', source_type='manual')
    assert build_restore_updates(meta, [change]) == {'title': ''}


def test_restore_action_creates_new_history_records(monkeypatch):
    session = _memory_session()
    _, change = _add_change(session, 'book', 'a.mp3', 'title', 'Old', 'New', datetime.utcnow())
    meta = AudioFileMetadata(path='a.mp3', title='New')
    monkeypatch.setattr('metadata_collector.history_restore.write_audio_metadata', lambda path, updates: None)
    monkeypatch.setattr('metadata_collector.history_restore.read_audio_metadata', lambda path: AudioFileMetadata(path=path, title='Old'))
    group, changes = restore_selected_metadata(session, 'book', meta, [change])
    assert group.source_type == 'restore'
    rows = session.query(MetadataChange).filter_by(change_group_id=group.id).all()
    assert len(rows) == 1
    assert rows[0].tag_name == 'title'
    assert rows[0].old_value == 'New'
    assert rows[0].new_value == 'Old'
    assert changes == {'title': ('New', 'Old')}


def test_cover_restore_disabled():
    assert not is_restore_supported('cover_data_uri')
    assert not is_restore_supported('has_cover')
    meta = AudioFileMetadata(path='a.mp3', has_cover=True)
    change = MetadataChange(change_group_id=1, book_key='book', file_path='a.mp3', tag_name='cover_data_uri', old_value='data:image/png;base64,abc', new_value='', source_type='manual')
    assert build_restore_updates(meta, [change]) == {}
