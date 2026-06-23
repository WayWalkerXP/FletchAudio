from pathlib import Path

import pytest

from metadata_collector.conversion_runner import (
    ConversionProgressEvent,
    ConversionResult,
    ConversionStatus,
)
from metadata_collector.conversion_ui import (
    ARCHIVE_DIRECTORY_REQUIRED,
    FOLDER_CONVERSION_UNSUPPORTED,
    ConversionUiError,
    build_ui_conversion_settings,
    conversion_progress_status,
    conversion_result_status,
    prepare_conversion,
)
from metadata_collector.models import AudioFileMetadata, Book


def make_book(path: Path, *, folder=False, bitrate=64, channels=1) -> Book:
    return Book(
        "book",
        str(path),
        folder,
        [AudioFileMetadata(str(path), title="Title", author="Author", target_bitrate=bitrate, target_channels=channels)],
    )


def test_folder_book_conversion_is_blocked(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()

    with pytest.raises(ConversionUiError, match=FOLDER_CONVERSION_UNSUPPORTED):
        prepare_conversion(make_book(book_dir, folder=True), {"conversion_output_dir": tmp_path, "archive_dir": tmp_path})


def test_missing_output_directory_prevents_conversion(tmp_path):
    source = tmp_path / "book.mp3"
    source.write_bytes(b"audio")

    with pytest.raises(ConversionUiError, match="not configured"):
        prepare_conversion(make_book(source), {})


def test_missing_archive_directory_prevents_conversion_planning(tmp_path):
    source = tmp_path / "book.mp3"
    source.write_bytes(b"audio")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with pytest.raises(ConversionUiError, match="Archive Directory is not configured"):
        prepare_conversion(make_book(source), {"conversion_output_dir": str(output_dir)})


def test_invalid_dry_run_plan_is_not_executable(tmp_path):
    source = tmp_path / "book.mp3"
    source.write_bytes(b"audio")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    archive_dir = tmp_path / "archive"

    prepared = prepare_conversion(
        make_book(source, bitrate=None),
        {"conversion_output_dir": str(output_dir), "archive_dir": str(archive_dir)},
    )

    assert prepared.plan.status == "invalid"
    assert any("target bitrate" in error for error in prepared.plan.errors)


def test_progress_event_becomes_running_status(tmp_path):
    event = ConversionProgressEvent(
        stage="converting",
        message="Converting audio",
        source_path=tmp_path / "book.mp3",
        final_output_path=tmp_path / "output.m4b",
    )

    status = conversion_progress_status(event)

    assert status.state == "running"
    assert status.stage == "converting"
    assert status.message == "Converting audio"
    assert status.output_path == tmp_path / "output.m4b"


def test_successful_result_becomes_clear_user_facing_status(tmp_path):
    output = tmp_path / "Author - Title.m4b"
    result = ConversionResult(
        status=ConversionStatus.SUCCESS,
        message="Conversion completed successfully",
        source_path=tmp_path / "book.mp3",
        final_output_path=output,
    )

    status = conversion_result_status(result)

    assert status.state == "success"
    assert status.message == f"Conversion completed successfully: {output}"
    assert status.output_path == output


def test_ui_settings_disable_source_archiving(tmp_path):
    archive_dir = tmp_path / "archive"
    settings = build_ui_conversion_settings({"conversion_output_dir": str(tmp_path), "archive_dir": str(archive_dir)})

    assert settings.output_dir == tmp_path
    assert settings.processed_dir == archive_dir
    assert settings.archive_original is True


def test_main_window_wires_plan_action_and_output_directory_setting():
    source = Path("metadata_collector/app.py").read_text()

    assert "ft.Button('Plan Conversion'" in source
    assert "prepared=prepare_conversion(book, settings)" in source
    assert "await asyncio.to_thread(" in source
    assert "run_conversion," in source
    assert "label='Conversion Output Directory'" in source
    assert "label='Archive Directory'" in source
    assert "settings['archive_dir']=" in source
    assert "def close_conversion_result_dialog" in source
    assert "final_status.state == 'success'" in source
    assert "scan()" in source.split("def close_conversion_result_dialog", 1)[1].split("result_dialog=ft.AlertDialog", 1)[0]


def test_archive_required_message_points_to_settings():
    assert "Settings > Directories" in ARCHIVE_DIRECTORY_REQUIRED
