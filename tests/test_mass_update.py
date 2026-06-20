from metadata_collector.mass_update import preview_mass_update
from metadata_collector.models import AudioFileMetadata

def test_mass_update_placeholder_formatting():
    f=AudioFileMetadata(path='/books/Book/ch1.m4b', track=1, album='Album', author='Auth')
    assert preview_mass_update([f], 'title', 'Chapter %track% - %filename% - %folder%')[0]['new_value']=='Chapter 1 - ch1 - Book'

def test_zero_padded_track_formatting():
    f=AudioFileMetadata(path='/b/ch1.m4b', track=3)
    assert preview_mass_update([f], 'title', 'Chapter %track:02%')[0]['new_value']=='Chapter 03'

from metadata_collector.mass_update import guess_track_number_from_filename, format_track_number, track_sort_key


def test_guess_track_number_supported_filename_prefixes():
    examples = [
        '01_Some_Track.mp3',
        '1_Some_Track.mp3',
        '1. Some Track.mp3',
        '1 Some Track.mp3',
        '[01] Some Track.mp3',
        '(01) Some Track.mp3',
    ]
    assert [guess_track_number_from_filename(name) for name in examples] == [1, 1, 1, 1, 1, 1]


def test_guess_track_number_rejects_invalid_or_non_positive_prefixes():
    assert guess_track_number_from_filename('Some Track 01.mp3') is None
    assert guess_track_number_from_filename('0 - Intro.mp3') is None
    assert guess_track_number_from_filename('01Intro.mp3') is None


def test_track_number_formatting_uses_dynamic_minimum_width():
    assert format_track_number(1, 2) == '01'
    assert format_track_number(38, 3) == '038'
    assert format_track_number(1000, 4) == '1000'


def test_track_sort_key_is_numeric_aware():
    values = ['1', '10', '003', '2', '100', 'abc']
    assert sorted(values, key=track_sort_key) == ['1', '2', '003', '10', '100', 'abc']
