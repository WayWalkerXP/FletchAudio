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


def test_mass_update_row_changed_compares_current_to_original(tmp_path):
    from metadata_collector.mass_update import MassUpdateTrackRow

    row = MassUpdateTrackRow(tmp_path / 'one.mp3', 'one.mp3', '01', 'Old', '01', 'Old')
    assert not row.changed
    row.selected = False
    assert not row.changed
    row.track = '02'
    assert row.changed
    row.track = '01'
    assert not row.changed
    row.title = 'New'
    assert row.changed


def test_save_track_title_rows_writes_only_changed_rows_and_updates_originals(monkeypatch, tmp_path):
    from metadata_collector import mass_update
    from metadata_collector.mass_update import MassUpdateTrackRow

    unchanged = MassUpdateTrackRow(tmp_path / 'one.mp3', 'one.mp3', '01', 'One', '01', 'One')
    changed = MassUpdateTrackRow(tmp_path / 'two.mp3', 'two.mp3', '02', 'Two', '03', 'Two Revised')
    unreadable = MassUpdateTrackRow(tmp_path / 'bad.mp3', 'bad.mp3', '', '', '04', 'Bad', readable=False)
    writes = []

    def fake_write(path, updates):
        writes.append((path, updates))

    monkeypatch.setattr(mass_update, 'write_audio_metadata', fake_write)

    successes, unchanged_count, failures = mass_update.save_track_title_rows([unchanged, changed, unreadable])

    assert successes == 1
    assert unchanged_count == 1
    assert failures == []
    assert writes == [(str(changed.path), {'track': '03', 'title': 'Two Revised'})]
    assert changed.original_track == '03'
    assert changed.original_title == 'Two Revised'
    assert not changed.changed


def test_save_track_title_rows_keeps_failed_rows_dirty(monkeypatch, tmp_path):
    from metadata_collector import mass_update
    from metadata_collector.mass_update import MassUpdateTrackRow

    row = MassUpdateTrackRow(tmp_path / 'fail.mp3', 'fail.mp3', '01', 'Old', '02', 'New')

    def fake_write(path, updates):
        raise RuntimeError('boom')

    monkeypatch.setattr(mass_update, 'write_audio_metadata', fake_write)

    successes, unchanged_count, failures = mass_update.save_track_title_rows([row])

    assert successes == 0
    assert unchanged_count == 0
    assert len(failures) == 1
    assert failures[0][0] is row
    assert row.original_track == '01'
    assert row.original_title == 'Old'
    assert row.changed

from metadata_collector.mass_update import guess_title_from_filename


def test_guess_title_from_filename_supported_prefixes():
    examples = {
        '01. Chapter 1.mp3': 'Chapter 1',
        '38 - Chapter 38.m4b': 'Chapter 38',
        '24. Chapter 8 - Yesterday.mp3': 'Chapter 8 - Yesterday',
        '12 - A New Day.mp3': 'A New Day',
        '01_Some_Track.mp3': 'Some_Track',
        '1 Some Track.mp3': 'Some Track',
        '[01] Some Track.mp3': 'Some Track',
        '(01) Some Track.mp3': 'Some Track',
        '001 - Title.mp3': 'Title',
    }
    assert {name: guess_title_from_filename(name) for name in examples} == examples



def test_guess_title_from_filename_strips_book_title_prefix_before_chapter_marker():
    examples = {
        'Imperial Summoner Mage Academy 2 - 01 - Opening Credits.mp3': '01 - Opening Credits',
        'Some Book Title - Chapter 4.mp3': 'Chapter 4',
        'Some Book Title - Book 2 Chapter 10.mp3': 'Book 2, Chapter 10',
        'Some Book Title - Part 3.mp3': 'Part 3',
    }
    assert {name: guess_title_from_filename(name) for name in examples} == examples


def test_guess_title_from_filename_normalizes_book_chapter_titles():
    assert guess_title_from_filename('A Tale of Two Cities - Book 2 Chapter 10.mp3') == 'Book 2, Chapter 10'
    assert guess_title_from_filename('Book 2 Chapter 10.mp3') == 'Book 2, Chapter 10'


def test_guess_title_from_filename_preserves_existing_non_chapter_prefix_behavior():
    assert guess_title_from_filename('The Tomb of Hercules 03.mp3') == 'The Tomb of Hercules 03'
    assert guess_title_from_filename('CD 04 - The Hunt For Atlantis.mp3') == 'CD 04 - The Hunt For Atlantis'

def test_guess_title_from_filename_uses_stem_for_non_numeric_and_ignores_path():
    assert guess_title_from_filename('/tmp/books/Prologue.mp3') == 'Prologue'
    assert guess_title_from_filename('/tmp/books/Chapter One.m4b') == 'Chapter One'


def test_guess_title_from_filename_rejects_empty_results():
    assert guess_title_from_filename('01.mp3') is None
    assert guess_title_from_filename('01 - .mp3') is None
    assert guess_title_from_filename('[01].mp3') is None
    assert guess_title_from_filename('   ') is None


def test_set_title_track_offset_parsing_and_padding():
    from metadata_collector.mass_update import apply_track_offset, parse_track_offset

    assert parse_track_offset(None) == 0
    assert parse_track_offset('') == 0
    assert parse_track_offset(' -10 ') == -10
    assert apply_track_offset('03', 0) == '03'
    assert apply_track_offset('03', -1) == '02'
    assert apply_track_offset('003', -1) == '002'
    assert apply_track_offset('3', -1) == '2'
    assert apply_track_offset('10', 5) == '15'
    assert apply_track_offset('01', -1) is None
    assert apply_track_offset('ABC', 0) is None


def test_set_title_template_validation_and_rendering(tmp_path):
    from metadata_collector.mass_update import MassUpdateTrackRow, render_title_template, validate_title_template

    row = MassUpdateTrackRow(tmp_path / '01 - Opening Credits.mp3', '01 - Opening Credits.mp3', '03', 'Old', '03', 'Current')
    assert validate_title_template('Chapter %track%')[0]
    assert validate_title_template('%filename% - %title%')[0]
    assert not validate_title_template('Part %disc%')[0]
    assert not validate_title_template('   ')[0]
    assert render_title_template('Chapter %track%', row, -1) == 'Chapter 02'
    assert render_title_template('%filename% - %title%', row, -99) == '01 - Opening Credits - Current'
