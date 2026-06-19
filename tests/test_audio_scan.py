from metadata_collector.audio_scan import scan_directory
from metadata_collector.models import AudioFileMetadata


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('audio')


def _patch_reader(monkeypatch):
    def fake_read_audio_metadata(path):
        return AudioFileMetadata(path=path)
    monkeypatch.setattr('metadata_collector.audio_scan.read_audio_metadata', fake_read_audio_metadata)


def test_root_audio_files_are_single_file_books(tmp_path, monkeypatch):
    _patch_reader(monkeypatch)
    for filename in ['Agent Zero.m4a', 'File Zero.m4a', 'Hunting Zero.m4a']:
        _touch(tmp_path / filename)

    books, errors = scan_directory(str(tmp_path))

    assert errors == []
    assert len(books) == 3
    assert all(not book.is_folder_book for book in books)
    assert [book.path for book in books] == [
        str(tmp_path / 'Agent Zero.m4a'),
        str(tmp_path / 'File Zero.m4a'),
        str(tmp_path / 'Hunting Zero.m4a'),
    ]


def test_only_subfolders_with_multiple_direct_audio_files_are_folder_books(tmp_path, monkeypatch):
    _patch_reader(monkeypatch)
    _touch(tmp_path / 'Agent Zero.m4a')
    _touch(tmp_path / 'My Folder Book' / '001.mp3')
    _touch(tmp_path / 'My Folder Book' / '002.mp3')
    _touch(tmp_path / 'Single In Folder' / 'only.m4b')
    _touch(tmp_path / 'Parent' / 'direct.mp3')
    _touch(tmp_path / 'Parent' / 'Nested' / '001.mp3')
    _touch(tmp_path / 'Parent' / 'Nested' / '002.mp3')

    books, errors = scan_directory(str(tmp_path))

    assert errors == []
    books_by_path = {book.path: book for book in books}
    assert books_by_path[str(tmp_path / 'Agent Zero.m4a')].is_folder_book is False
    assert books_by_path[str(tmp_path / 'My Folder Book')].is_folder_book is True
    assert [file.path for file in books_by_path[str(tmp_path / 'My Folder Book')].files] == [
        str(tmp_path / 'My Folder Book' / '001.mp3'),
        str(tmp_path / 'My Folder Book' / '002.mp3'),
    ]
    assert books_by_path[str(tmp_path / 'Single In Folder' / 'only.m4b')].is_folder_book is False
    assert books_by_path[str(tmp_path / 'Parent' / 'direct.mp3')].is_folder_book is False
    assert books_by_path[str(tmp_path / 'Parent' / 'Nested')].is_folder_book is True
