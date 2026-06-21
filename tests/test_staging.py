from pathlib import Path

from metadata_collector.models import AudioFileMetadata, Book
from metadata_collector.staging import (
    StagingCandidate,
    candidates_from_books,
    move_to_staging,
    safe_move_to_staging,
    verify_copy,
    destination_for,
)

def test_candidates_include_ready_file_and_folder_once():
    books = [
        Book('file-ready', '/work/Ready.m4b', False, [AudioFileMetadata('/work/Ready.m4b', target_bitrate=64, target_channels=1)]),
        Book('file-missing', '/work/Missing.m4b', False, [AudioFileMetadata('/work/Missing.m4b', target_bitrate=64)]),
        Book('folder-ready', '/work/Folder', True, [
            AudioFileMetadata('/work/Folder/01.mp3', target_bitrate=48, target_channels=2),
            AudioFileMetadata('/work/Folder/02.mp3', target_bitrate=48, target_channels=2),
        ]),
        Book('folder-missing', '/work/Incomplete', True, [
            AudioFileMetadata('/work/Incomplete/01.mp3', target_bitrate=48, target_channels=2),
            AudioFileMetadata('/work/Incomplete/02.mp3', target_bitrate=48),
        ]),
    ]

    candidates = candidates_from_books(books)

    assert [(c.display_name, c.item_type, c.target_bitrate, c.target_channels) for c in candidates] == [
        ('Ready.m4b', 'file', '64', '1'),
        ('Folder', 'folder', '48', '2'),
    ]

def test_move_to_staging_skips_existing_destination(tmp_path):
    source = tmp_path / 'work' / 'Book.m4b'
    staging = tmp_path / 'staging'
    source.parent.mkdir()
    staging.mkdir()
    source.write_bytes(b'source')
    (staging / source.name).write_bytes(b'existing')

    result = move_to_staging(StagingCandidate(source, 'Book.m4b', 'file', '64', '1'), staging)

    assert result.status == 'skipped'
    assert source.exists()
    assert (staging / source.name).read_bytes() == b'existing'

def test_safe_move_copies_verifies_and_deletes_file(tmp_path):
    source = tmp_path / 'work' / 'Book.m4b'
    staging = tmp_path / 'staging'
    source.parent.mkdir()
    staging.mkdir()
    source.write_bytes(b'audio')

    result = safe_move_to_staging(StagingCandidate(source, 'Book.m4b', 'file', '64', '1'), staging)

    assert result.status == 'moved'
    assert not source.exists()
    assert (staging / 'Book.m4b').read_bytes() == b'audio'

def test_verify_copy_checks_folder_file_sizes(tmp_path):
    source = tmp_path / 'work' / 'Folder'
    destination = tmp_path / 'staging' / 'Folder'
    (source / 'sub').mkdir(parents=True)
    (destination / 'sub').mkdir(parents=True)
    (source / 'sub' / '01.mp3').write_bytes(b'1234')
    (destination / 'sub' / '01.mp3').write_bytes(b'1234')

    assert verify_copy(source, destination)

    (destination / 'sub' / '01.mp3').write_bytes(b'123')
    assert not verify_copy(source, destination)

def test_folder_book_staging_candidate_uses_classified_folder_and_shallow_destination():
    folder_book = Book('folder-ready', '/work/Author/Series/Book B', True, [
        AudioFileMetadata('/work/Author/Series/Book B/01.mp3', target_bitrate=48, target_channels=2),
        AudioFileMetadata('/work/Author/Series/Book B/02.mp3', target_bitrate=48, target_channels=2),
    ])

    candidates = candidates_from_books([folder_book])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_path == Path('/work/Author/Series/Book B')
    assert candidate.item_type == 'folder'
    assert destination_for(candidate, Path('/staging')) == Path('/staging/Book B')

def test_single_file_staging_candidate_uses_audio_file_and_shallow_destination():
    single_file_book = Book('file-ready', '/work/Author/Book A/book-a.m4b', False, [
        AudioFileMetadata('/work/Author/Book A/book-a.m4b', target_bitrate=64, target_channels=1),
    ])

    candidates = candidates_from_books([single_file_book])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_path == Path('/work/Author/Book A/book-a.m4b')
    assert candidate.item_type == 'file'
    assert destination_for(candidate, Path('/staging')) == Path('/staging/book-a.m4b')

def test_safe_move_to_staging_skips_existing_destination(tmp_path):
    source = tmp_path / 'work' / 'Book.m4b'
    staging = tmp_path / 'staging'
    source.parent.mkdir()
    staging.mkdir()
    source.write_bytes(b'source')
    (staging / source.name).write_bytes(b'existing')

    result = safe_move_to_staging(StagingCandidate(source, 'Book.m4b', 'file', '64', '1'), staging)

    assert result.status == 'skipped'
    assert source.exists()
    assert (staging / source.name).read_bytes() == b'existing'

def test_move_to_staging_moves_folder_book_without_parent_tree(tmp_path):
    source = tmp_path / 'work' / 'Author' / 'Series' / 'Book B'
    staging = tmp_path / 'staging'
    source.mkdir(parents=True)
    staging.mkdir()
    (source / '01.mp3').write_bytes(b'audio')

    result = move_to_staging(StagingCandidate(source, 'Book B', 'folder', '48', '2'), staging)

    assert result.status == 'moved'
    assert not source.exists()
    assert (staging / 'Book B' / '01.mp3').read_bytes() == b'audio'
    assert not (staging / 'Author').exists()
