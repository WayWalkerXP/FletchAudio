import pytest
from pathlib import Path

from metadata_collector.conversion_adapter import (
    ConversionRequest,
    ConversionRequestError,
    build_conversion_request,
)
from metadata_collector.models import AudioFileMetadata, Book


def test_single_file_book_builds_conversion_request():
    file_meta = AudioFileMetadata(
        "/library/book.m4b",
        title="Book Title",
        author="Author Name",
        asin="B000TEST",
        target_bitrate=64,
        target_channels=1,
        dramatic_audio=False,
    )
    book = Book("book-key", "/library/book.m4b", False, [file_meta])

    request = build_conversion_request(book)

    assert isinstance(request, ConversionRequest)
    assert request.book_key == "book-key"
    assert request.source_path == Path("/library/book.m4b")
    assert request.is_folder_book is False
    assert request.files == (Path("/library/book.m4b"),)
    assert request.target_bitrate == 64
    assert request.target_channels == 1
    assert request.dramatic_audio is False
    assert request.metadata["title"] == "Book Title"
    assert request.metadata["author"] == "Author Name"
    assert request.metadata["asin"] == "B000TEST"


def test_folder_book_builds_request_with_all_file_paths():
    book = Book(
        "folder-key",
        "/library/Folder Book",
        True,
        [
            AudioFileMetadata("/library/Folder Book/01.mp3", title="Part 1", target_bitrate="48", target_channels="2", dramatic_audio=True),
            AudioFileMetadata("/library/Folder Book/02.mp3", title="Part 2", target_bitrate=48, target_channels=2, dramatic_audio=True),
        ],
    )

    request = build_conversion_request(book)

    assert request.source_path == Path("/library/Folder Book")
    assert request.is_folder_book is True
    assert request.files == (
        Path("/library/Folder Book/01.mp3"),
        Path("/library/Folder Book/02.mp3"),
    )
    assert request.target_bitrate == 48
    assert request.target_channels == 2
    assert request.dramatic_audio is True


def test_missing_target_values_normalize_to_none():
    book = Book(
        "missing-targets",
        "/library/book.mp3",
        False,
        [AudioFileMetadata("/library/book.mp3", target_bitrate="Unset", target_channels="")],
    )

    request = build_conversion_request(book)

    assert request.target_bitrate is None
    assert request.target_channels is None


@pytest.mark.parametrize(
    ("target_bitrate", "target_channels"),
    [(40, 1), (64, 3), ("fast", 1)],
)
def test_invalid_target_values_raise_validation_error(target_bitrate, target_channels):
    book = Book(
        "invalid-targets",
        "/library/book.mp3",
        False,
        [AudioFileMetadata("/library/book.mp3", target_bitrate=target_bitrate, target_channels=target_channels)],
    )

    with pytest.raises(ConversionRequestError):
        build_conversion_request(book)


def test_metadata_fields_are_copied_without_mutating_original_objects():
    file_meta = AudioFileMetadata(
        "/library/book.mp3",
        title="Original Title",
        author="Original Author",
        genres=["Fantasy", "Adventure"],
        target_bitrate=128,
        target_channels=2,
    )
    book = Book("copy-test", "/library/book.mp3", False, [file_meta])

    request = build_conversion_request(book)
    request.metadata["title"] = "Changed Request Title"
    request.metadata["genres"] = "Changed Genre"

    assert file_meta.title == "Original Title"
    assert file_meta.author == "Original Author"
    assert file_meta.genres == ["Fantasy", "Adventure"]
    assert file_meta.target_bitrate == 128
    assert file_meta.target_channels == 2
    assert book.files == [file_meta]
