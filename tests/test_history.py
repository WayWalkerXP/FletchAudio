import json
from metadata_collector.history import metadata_diff, selectable_restore_values
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
