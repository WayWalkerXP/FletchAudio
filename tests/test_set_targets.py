from pathlib import Path

from metadata_collector.audio_tags import diff_metadata
from metadata_collector.app import target_settings_status
from metadata_collector.models import AudioFileMetadata, Book


def test_target_fields_are_diffable_workflow_tags():
    current = AudioFileMetadata('/tmp/book.mp3', target_bitrate=64, target_channels=1, dramatic_audio=False)

    assert diff_metadata(current, {'target_bitrate': 128, 'target_channels': 2, 'dramatic_audio': True}) == {
        'target_bitrate': 128,
        'target_channels': 2,
        'dramatic_audio': True,
    }


def test_set_targets_ui_uses_required_labels_and_source_type():
    app_source = Path('metadata_collector/app.py').read_text()

    assert "ft.Button('Set Targets'" in app_source
    assert "Set Targets and Dramatic Audio" in app_source
    assert "source_type='set_targets'" in app_source
    assert "Saving target settings..." in app_source
    assert "Target settings saved." in app_source


def make_book(files, is_folder_book=False):
    return Book(key='book', path='/tmp/book', is_folder_book=is_folder_book, files=files)


def test_target_settings_status_green_for_configured_single_file_without_dramatic_audio():
    book = make_book([AudioFileMetadata('/tmp/book.mp3', target_bitrate=64, target_channels=1, dramatic_audio=None)])

    assert target_settings_status(book) == 'green'


def test_target_settings_status_red_for_missing_or_invalid_targets():
    assert target_settings_status(make_book([AudioFileMetadata('/tmp/book.mp3', target_bitrate=None, target_channels=1)])) == 'red'
    assert target_settings_status(make_book([AudioFileMetadata('/tmp/book.mp3', target_bitrate=64, target_channels=3)])) == 'red'


def test_target_settings_status_yellow_for_inconsistent_folder_targets():
    book = make_book([
        AudioFileMetadata('/tmp/book/01.mp3', target_bitrate=64, target_channels=1),
        AudioFileMetadata('/tmp/book/02.mp3', target_bitrate=128, target_channels=1),
    ], is_folder_book=True)

    assert target_settings_status(book) == 'yellow'


def test_target_settings_status_green_for_consistent_folder_targets():
    book = make_book([
        AudioFileMetadata('/tmp/book/01.mp3', target_bitrate=64, target_channels=2),
        AudioFileMetadata('/tmp/book/02.mp3', target_bitrate='64', target_channels='2'),
    ], is_folder_book=True)

    assert target_settings_status(book) == 'green'
