from __future__ import annotations

from pathlib import Path

from metadata_collector.alchemist_engine.errors import ExternalToolError
from metadata_collector.alchemist_engine.ffmpeg import CommandResult
from metadata_collector.alchemist_engine.models import AudioInfo
from metadata_collector.conversion_adapter import ConversionRequest, ConversionSettings
from metadata_collector.conversion_runner import ConversionRunner, ConversionStatus


class FakeAnalyzer:
    def probe(self, path: Path) -> AudioInfo:
        return AudioInfo(path, 64_000, 1, "aac", 60.0, 0)


class FakeValidator:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid

    def validate(self, source_info, plan, output_path) -> bool:
        return self.valid and output_path.exists()


def setup_conversion(tmp_path: Path, *, folder: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "output"
    processed_dir = tmp_path / "processed"
    output_dir.mkdir()
    processed_dir.mkdir()
    if folder:
        source = tmp_path / "book"
        source.mkdir()
        track = source / "01.mp3"
        track.write_bytes(b"source")
        files = (track,)
    else:
        source = tmp_path / "book.mp3"
        source.write_bytes(b"source")
        files = (source,)
    request = ConversionRequest(
        book_key="book",
        source_path=source,
        is_folder_book=folder,
        files=files,
        target_bitrate=64,
        target_channels=1,
        dramatic_audio=True,
        metadata={
            "title": "Title",
            "author": "Author",
            "narrator": "Narrator",
            "series": "Series",
            "series_sequence": "2",
            "asin": "ASIN",
            "target_bitrate": "64",
            "target_channels": "1",
        },
    )
    settings = ConversionSettings(output_dir=output_dir, processed_dir=processed_dir)
    return request, settings


def successful_command(command: list[str]) -> CommandResult:
    Path(command[-1]).write_bytes(b"converted")
    return CommandResult(command, 0, "", "")


def test_successful_conversion_writes_metadata_promotes_and_archives(tmp_path):
    request, settings = setup_conversion(tmp_path)
    writes = []
    runner = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
        metadata_writer=lambda path, tags: writes.append((Path(path), tags)),
        cover_copier=lambda source, destination: True,
    )

    result = runner.run(request)

    assert result.status == ConversionStatus.SUCCESS
    assert result.final_output_path.read_bytes() == b"converted"
    assert result.archived_path.read_bytes() == b"source"
    assert not request.source_path.exists()
    assert not result.temporary_output_path.exists()
    assert writes[0][0].name.endswith(".tmp.m4b")
    assert writes[0][1]["dramatic_audio"] == "true"
    assert "target_bitrate" not in writes[0][1]
    assert "target_channels" not in writes[0][1]


def test_successful_conversion_attempts_embedded_cover_copy(tmp_path):
    request, settings = setup_conversion(tmp_path)
    cover_calls = []
    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
        metadata_writer=lambda path, tags: None,
        cover_copier=lambda source, destination: cover_calls.append((source, destination)) or True,
    ).run(request)

    assert result.status == ConversionStatus.SUCCESS
    assert cover_calls == [(str(request.source_path), str(result.temporary_output_path))]


def test_cover_copy_failure_does_not_fail_successful_conversion(tmp_path):
    request, settings = setup_conversion(tmp_path)

    def fail_cover_copy(source, destination):
        raise ValueError("cover failed")

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
        metadata_writer=lambda path, tags: None,
        cover_copier=fail_cover_copy,
    ).run(request)

    assert result.status == ConversionStatus.SUCCESS


def test_archive_collision_uses_numeric_suffix_after_successful_conversion(tmp_path):
    request, settings = setup_conversion(tmp_path)
    existing_archive = settings.processed_dir / request.source_path.name
    existing_archive.write_bytes(b"existing")

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
        metadata_writer=lambda path, tags: None,
        cover_copier=lambda source, destination: True,
    ).run(request)

    assert result.status == ConversionStatus.SUCCESS
    assert result.archived_path == settings.processed_dir / "book (1).mp3"
    assert result.archived_path.read_bytes() == b"source"
    assert existing_archive.read_bytes() == b"existing"


def test_archive_failure_keeps_successful_conversion_and_source_file(tmp_path):
    request, settings = setup_conversion(tmp_path)

    def fail_archive(source, archive_dir):
        raise OSError("archive failed")

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
        metadata_writer=lambda path, tags: None,
        cover_copier=lambda source, destination: True,
        archive_mover=fail_archive,
    ).run(request)

    assert result.status == ConversionStatus.SUCCESS
    assert result.final_output_path.exists()
    assert request.source_path.exists()
    assert result.archived_path is None
    assert "could not be moved to the Archive Directory" in result.message


def test_ffmpeg_failure_leaves_source_and_removes_temp(tmp_path):
    request, settings = setup_conversion(tmp_path)

    def fail(command):
        Path(command[-1]).write_bytes(b"partial")
        return CommandResult(command, 1, "", "encoder failed")

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=fail,
    ).run(request)

    assert result.status == ConversionStatus.FAILED
    assert request.source_path.exists()
    assert not (settings.processed_dir / request.source_path.name).exists()
    assert not result.temporary_output_path.exists()
    assert not result.final_output_path.exists()


def test_missing_ffmpeg_returns_clear_user_facing_failure(tmp_path):
    request, settings = setup_conversion(tmp_path)

    def missing_ffmpeg(command):
        raise ExternalToolError(
            "FFmpeg executable not found. Install FFmpeg or configure its path before converting."
        )

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=missing_ffmpeg,
    ).run(request)

    assert result.status == ConversionStatus.FAILED
    assert result.message == "Conversion failed"
    assert result.error_details == (
        "FFmpeg executable not found. Install FFmpeg or configure its path before converting."
    )
    assert request.source_path.exists()
    assert not result.temporary_output_path.exists()


def test_missing_source_file_returns_clear_failure(tmp_path):
    request, settings = setup_conversion(tmp_path)
    request.source_path.unlink()

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
    ).run(request)

    assert result.status == ConversionStatus.FAILED
    assert "Source file does not exist:" in result.error_details


def test_validation_failure_leaves_source_and_removes_temp(tmp_path):
    request, settings = setup_conversion(tmp_path)
    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(False),
        command_runner=successful_command,
    ).run(request)

    assert result.status == ConversionStatus.FAILED
    assert request.source_path.exists()
    assert not result.temporary_output_path.exists()


def test_metadata_failure_does_not_promote_or_archive(tmp_path):
    request, settings = setup_conversion(tmp_path)

    def fail_metadata(path, tags):
        raise ValueError("metadata failed")

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
        metadata_writer=fail_metadata,
    ).run(request)

    assert result.status == ConversionStatus.FAILED
    assert request.source_path.exists()
    assert not result.final_output_path.exists()
    assert not result.temporary_output_path.exists()


def test_existing_destination_is_not_overwritten(tmp_path):
    request, settings = setup_conversion(tmp_path)
    destination = settings.output_dir / "Author - Title.m4b"
    destination.write_bytes(b"existing")
    calls = []

    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=lambda command: calls.append(command),
    ).run(request)

    assert result.status == ConversionStatus.FAILED
    assert destination.read_bytes() == b"existing"
    assert request.source_path.exists()
    assert calls == []


def test_folder_book_is_rejected_before_conversion_work(tmp_path):
    request, settings = setup_conversion(tmp_path, folder=True)
    calls = []
    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        command_runner=lambda command: calls.append(command),
    ).run(request)

    assert result.status == ConversionStatus.UNSUPPORTED
    assert request.source_path.exists()
    assert calls == []


def test_progress_events_cover_success_and_failure_stages(tmp_path):
    request, settings = setup_conversion(tmp_path)
    events = []
    result = ConversionRunner(
        settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=successful_command,
        metadata_writer=lambda path, tags: None,
    ).run(request, events.append)

    assert result.status == ConversionStatus.SUCCESS
    assert [event.stage for event in events] == [
        "planning",
        "probing",
        "converting",
        "validating",
        "writing_metadata",
        "promoting",
        "archiving",
        "complete",
    ]

    failed_request, failed_settings = setup_conversion(tmp_path / "failed")
    failed_events = []
    failed = ConversionRunner(
        failed_settings,
        analyzer=FakeAnalyzer(),
        validator=FakeValidator(),
        command_runner=lambda command: CommandResult(command, 1, "", "failed"),
    ).run(failed_request, failed_events.append)

    assert failed.status == ConversionStatus.FAILED
    assert failed_events[-1].stage == "failed"
