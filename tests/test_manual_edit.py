import pytest

from metadata_collector.manual_edit import CoverEditState, build_manual_metadata_diff, filter_manual_updates_for_file
from metadata_collector.models import AudioFileMetadata


def test_manual_edit_diff_generation():
    current = AudioFileMetadata('/tmp/book.mp3', title='Old', author='Same')

    assert build_manual_metadata_diff(current, {'title': 'New', 'author': 'Same'}) == {'title': 'New'}


def test_manual_edit_cleared_field_creates_intentional_change():
    current = AudioFileMetadata('/tmp/book.mp3', title='Old')

    assert build_manual_metadata_diff(current, {'title': ''}) == {'title': ''}


def test_manual_edit_unchanged_fields_are_ignored():
    current = AudioFileMetadata('/tmp/book.mp3', title='Same', asin='B000TEST')

    assert build_manual_metadata_diff(current, {'title': 'Same', 'asin': ' b000test '}) == {}


def test_manual_edit_normalizes_genres_before_write():
    current = AudioFileMetadata('/tmp/book.mp3', genres=[])

    assert build_manual_metadata_diff(current, {'genres': r'One\Two'}) == {'genres': r'One\\Two'}


def test_manual_edit_normalizes_asin():
    current = AudioFileMetadata('/tmp/book.mp3', asin='OLD')

    assert build_manual_metadata_diff(current, {'asin': ' b0abc123 '}) == {'asin': 'B0ABC123'}


def test_manual_edit_validates_published_year():
    current = AudioFileMetadata('/tmp/book.mp3', published_year='2020')

    with pytest.raises(ValueError, match='four digits'):
        build_manual_metadata_diff(current, {'published_year': '20AB'})


def test_manual_edit_cover_replacement_state():
    current = AudioFileMetadata('/tmp/book.mp3', has_cover=True, cover_data_uri='data:image/jpeg;base64,old')

    assert build_manual_metadata_diff(current, {}, CoverEditState(path='/tmp/new.jpg')) == {'cover_path': '/tmp/new.jpg'}


def test_manual_edit_cover_deletion_state():
    current = AudioFileMetadata('/tmp/book.mp3', has_cover=True, cover_data_uri='data:image/jpeg;base64,old')

    assert build_manual_metadata_diff(current, {}, CoverEditState(delete=True)) == {'delete_cover': True}


def test_folder_manual_updates_exclude_file_level_title_track_disc():
    updates = {'album': 'Album', 'title': 'Track title', 'track': '1', 'disc': '2'}

    assert filter_manual_updates_for_file(True, updates) == {'album': 'Album'}
