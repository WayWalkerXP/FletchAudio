from pathlib import Path

from metadata_collector.models import AudioFileMetadata, Book
from metadata_collector.move_library import (
    DUPLICATE_ASIN,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARN,
    apply_duplicate_result,
    dry_run,
    move_items,
    target_for_item,
    validate_item,
)


def make_book(path, *, author="Author", album="Album", series=None, sequence=None, asin=None, folder=False, files=None):
    if files is None:
        files = [AudioFileMetadata(str(path), author=author, album=album, series=series, series_sequence=sequence, asin=asin)]
    return Book("key-" + Path(path).name, str(path), folder, files)


def test_required_tag_validation_marks_ok_and_missing_fields(tmp_path):
    ok = validate_item(make_book(tmp_path / "book.m4b"), tmp_path, "staging")
    missing_author = validate_item(make_book(tmp_path / "a.m4b", author=" ", album="Album"), tmp_path, "staging")
    missing_album = validate_item(make_book(tmp_path / "b.m4b", author="Author", album=None), tmp_path, "staging")
    missing_both = validate_item(make_book(tmp_path / "c.m4b", author="", album=""), tmp_path, "staging")

    assert ok.status == STATUS_OK
    assert ok.selected is True
    assert ok.checkable is True
    assert missing_author.status == STATUS_ERROR
    assert missing_author.status_detail == "Missing: Author"
    assert missing_album.status_detail == "Missing: Album"
    assert missing_both.status_detail == "Missing: Author, Album"
    assert missing_both.selected is False
    assert missing_both.checkable is False


def test_target_path_construction_and_single_file_album_filename(tmp_path):
    item = validate_item(
        make_book(tmp_path / "source.m4b", author="WayWalker", album="This Escalated Quickly", series="Coding Adventures", sequence="01"),
        tmp_path,
        "converted",
    )

    target = target_for_item(item, tmp_path / "ABS")

    assert target.destination_folder == tmp_path / "ABS" / "WayWalker" / "Coding Adventures" / "01 This Escalated Quickly"
    assert target.target_paths == (target.destination_folder / "This Escalated Quickly.m4b",)


def test_folder_book_destination_preserves_original_filenames(tmp_path):
    source = tmp_path / "Tribulations"
    files = [
        AudioFileMetadata(str(source / "chapter_01.mp3"), author="Jack Johnson", album="Tribulations", series="My Life", series_sequence="01"),
        AudioFileMetadata(str(source / "chapter_02.mp3"), author="Jack Johnson", album="Tribulations", series="My Life", series_sequence="01"),
    ]
    item = validate_item(make_book(source, folder=True, files=files), tmp_path, "staging")

    target = target_for_item(item, tmp_path / "ABS")

    assert target.destination_folder == tmp_path / "ABS" / "Jack Johnson" / "My Life" / "01 Tribulations"
    assert target.target_paths == (
        target.destination_folder / "chapter_01.mp3",
        target.destination_folder / "chapter_02.mp3",
    )


def test_dry_run_detects_file_and_folder_collisions(tmp_path):
    single_source = tmp_path / "book.m4b"
    single_source.write_bytes(b"audio")
    single = validate_item(make_book(single_source, author="A", album="B"), tmp_path, "converted")
    existing_file = tmp_path / "ABS" / "A" / "B" / "B.m4b"
    existing_file.parent.mkdir(parents=True)
    existing_file.write_bytes(b"existing")

    folder_source = tmp_path / "Folder"
    folder_source.mkdir()
    folder_file = folder_source / "01.mp3"
    folder_file.write_bytes(b"audio")
    folder = validate_item(
        make_book(folder_source, folder=True, files=[AudioFileMetadata(str(folder_file), author="C", album="D")]),
        tmp_path,
        "staging",
    )
    (tmp_path / "ABS" / "C" / "D").mkdir(parents=True)

    rows = dry_run([single, folder], tmp_path / "ABS")

    assert [row.target_exists for row in rows] == ["Yes - File Exists", "Yes - Folder Exists"]


def test_duplicate_match_sets_warn_unchecked_and_active(tmp_path):
    item = validate_item(make_book(tmp_path / "book.m4b"), tmp_path, "converted")

    apply_duplicate_result(item, DUPLICATE_ASIN)

    assert item.status == STATUS_WARN
    assert item.duplicate == DUPLICATE_ASIN
    assert item.selected is False
    assert item.checkable is True


def test_move_folder_book_deletes_empty_source_folder(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    first = source / "01.mp3"
    second = source / "02.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    item = validate_item(
        make_book(
            source,
            folder=True,
            files=[
                AudioFileMetadata(str(first), author="Author", album="Album"),
                AudioFileMetadata(str(second), author="Author", album="Album"),
            ],
        ),
        tmp_path,
        "staging",
    )

    report = move_items([item], tmp_path / "ABS")

    assert (tmp_path / "ABS" / "Author" / "Album" / "01.mp3").read_bytes() == b"one"
    assert (tmp_path / "ABS" / "Author" / "Album" / "02.mp3").read_bytes() == b"two"
    assert not source.exists()
    assert report.source_folders_deleted == [str(source)]
