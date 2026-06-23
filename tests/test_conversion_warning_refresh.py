from pathlib import Path

from metadata_collector.app import sync_folder_book_metadata_from_rows
from metadata_collector.conversion_ui import prepare_conversion
from metadata_collector.mass_update import MassUpdateTrackRow
from metadata_collector.models import AudioFileMetadata, Book


def test_folder_conversion_warning_is_recalculated_after_track_metadata_update(tmp_path):
    folder = tmp_path / "Book"
    folder.mkdir()
    first = folder / "alpha.mp3"
    second = folder / "beta.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    archive_dir = tmp_path / "archive"

    book = Book(
        "book",
        str(folder),
        True,
        [
            AudioFileMetadata(str(first), title="Alpha", author="Author", album="Title", target_bitrate=64, target_channels=1),
            AudioFileMetadata(str(second), title="Beta", author="Author", album="Title", target_bitrate=64, target_channels=1),
        ],
    )
    settings = {"conversion_output_dir": output_dir, "archive_dir": archive_dir}

    first_plan = prepare_conversion(book, settings).plan

    assert any("ordering is ambiguous" in warning for warning in first_plan.warnings)

    sync_folder_book_metadata_from_rows(
        book,
        [
            MassUpdateTrackRow(first, first.name, "", "Alpha", "01", "Alpha"),
            MassUpdateTrackRow(second, second.name, "", "Beta", "02", "Beta"),
        ],
    )
    second_plan = prepare_conversion(book, settings).plan

    assert not any("ordering is ambiguous" in warning for warning in second_plan.warnings)
    assert second_plan.input_paths == (first, second)
