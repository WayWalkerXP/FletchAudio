import pytest

from metadata_collector.manual_edit import (
    CoverEditState,
    build_current_metadata_values,
    build_manual_metadata_diff,
    filter_manual_updates_for_file,
    has_manual_unsaved_changes,
    manual_changed_fields,
    manual_current_value,
    manual_edit_file_label,
    should_switch_manual_file,
    sorted_manual_edit_files,
)
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


def test_manual_edit_checked_boolean_creates_true_update():
    current = AudioFileMetadata('/tmp/book.mp3', explicit=False)

    assert build_manual_metadata_diff(current, {'explicit': True}) == {'explicit': True}


def test_manual_edit_unchecked_boolean_creates_false_update():
    current = AudioFileMetadata('/tmp/book.mp3', explicit=True, dramatic_audio=True)

    assert build_manual_metadata_diff(current, {'explicit': False, 'dramatic_audio': False}) == {'explicit': False, 'dramatic_audio': False}


def test_manual_edit_unchanged_false_boolean_is_ignored():
    current = AudioFileMetadata('/tmp/book.mp3', explicit=False, dramatic_audio=False)

    assert build_manual_metadata_diff(current, {'explicit': False, 'dramatic_audio': False}) == {}


def test_manual_edit_cover_replacement_state():
    current = AudioFileMetadata('/tmp/book.mp3', has_cover=True, cover_data_uri='data:image/jpeg;base64,old')

    assert build_manual_metadata_diff(current, {}, CoverEditState(path='/tmp/new.jpg')) == {'cover_path': '/tmp/new.jpg'}


def test_manual_edit_cover_deletion_state():
    current = AudioFileMetadata('/tmp/book.mp3', has_cover=True, cover_data_uri='data:image/jpeg;base64,old')

    assert build_manual_metadata_diff(current, {}, CoverEditState(delete=True)) == {'delete_cover': True}


def test_folder_manual_updates_exclude_file_level_title_track_disc():
    updates = {'album': 'Album', 'title': 'Track title', 'track': '1', 'disc': '2'}

    assert filter_manual_updates_for_file(True, updates) == {'album': 'Album'}


def test_manual_dirty_check_normalizes_unchanged_form_values():
    current = AudioFileMetadata('/tmp/book.mp3', title='Old', author=None, genres=['One', 'Two'], explicit=False, dramatic_audio=True)
    edited = {'title': ' Old ', 'author': '', 'genres': r'One\\Two', 'explicit': False, 'dramatic_audio': True}

    assert build_current_metadata_values(current)['genres'] == r'One\\Two'
    assert manual_changed_fields(current, edited, CoverEditState()) == {}
    assert not has_manual_unsaved_changes(current, edited, CoverEditState())


def test_manual_edit_detects_unsaved_text_and_cover_changes():
    current = AudioFileMetadata('/tmp/book.mp3', title='Old', has_cover=True, cover_data_uri='data:image/jpeg;base64,old')

    assert not has_manual_unsaved_changes(current, {'title': 'Old'}, CoverEditState())
    assert has_manual_unsaved_changes(current, {'title': 'New'}, CoverEditState())
    assert has_manual_unsaved_changes(current, {'title': 'Old'}, CoverEditState(delete=True))


def test_folder_manual_edit_files_sort_by_track_then_filename():
    files = [
        AudioFileMetadata('/book/b.mp3'),
        AudioFileMetadata('/book/02.mp3', track=2),
        AudioFileMetadata('/book/01.mp3', track=1),
        AudioFileMetadata('/book/a.mp3'),
    ]

    assert [file.path for file in sorted_manual_edit_files(files)] == ['/book/01.mp3', '/book/02.mp3', '/book/a.mp3', '/book/b.mp3']
    assert manual_edit_file_label(files[2]) == '1. 01.mp3'


def test_manual_edit_file_label_uses_filename_for_windows_paths():
    file = AudioFileMetadata(r'C:\\AB_Test\\Book\\CD 01 - The Hunt For Atlantis.mp3')

    assert manual_edit_file_label(file) == 'CD 01 - The Hunt For Atlantis.mp3'


def test_switching_with_no_unsaved_changes_switches_without_save():
    assert should_switch_manual_file(False, None) == (True, False)


def test_switch_decision_save_discard_cancel_behavior():
    assert should_switch_manual_file(True, 'save') == (True, True)
    assert should_switch_manual_file(True, 'discard') == (True, False)
    assert should_switch_manual_file(True, 'cancel') == (False, False)
    assert should_switch_manual_file(True, None) == (False, False)


def test_selected_file_metadata_loading_uses_selected_file_values():
    first = AudioFileMetadata('/book/01.mp3', title='One', track=1, genres=['A'])
    second = AudioFileMetadata('/book/02.mp3', title='Two', track=2, genres=['B', 'C'])

    assert manual_current_value(first, 'title') == 'One'
    assert manual_current_value(second, 'title') == 'Two'
    assert manual_current_value(second, 'genres') == r'B\\C'
