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
