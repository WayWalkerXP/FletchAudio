from __future__ import annotations

import subprocess
from pathlib import Path

from metadata_collector.conversion_adapter import ConversionRequest, ConversionSettings, ConversionTrack
from metadata_collector.conversion_planner import plan_conversion, plan_conversions


def make_request(
    source_path: Path,
    *,
    files: tuple[Path, ...] | None = None,
    is_folder_book: bool = False,
    metadata: dict[str, str] | None = None,
    target_bitrate: int | None = 64,
    target_channels: int | None = 1,
    tracks: tuple[ConversionTrack, ...] = (),
) -> ConversionRequest:
    return ConversionRequest(
        book_key="book-key",
        source_path=source_path,
        is_folder_book=is_folder_book,
        files=files or (source_path,),
        target_bitrate=target_bitrate,
        target_channels=target_channels,
        dramatic_audio=False,
        metadata=metadata or {"author": "Author Name", "album": "Book Title"},
        tracks=tracks,
    )


def test_single_file_planning_generates_expected_output_path(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = plan_conversion(
        make_request(source),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "planned"
    assert result.output_path == output_dir / "Author Name - Book Title.m4b"
    assert result.temporary_output_path == output_dir / "Author Name - Book Title.tmp.m4b"
    assert result.input_paths == (source,)
    assert result.selected_codec == "libfdk_aac"


def test_folder_book_planning_sorts_all_inputs_deterministically(tmp_path):
    source = tmp_path / "book"
    source.mkdir()
    tracks = (source / "03.mp3", source / "01.mp3", source / "02.mp3")
    for track in tracks:
        track.write_bytes(b"track")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = plan_conversion(
        make_request(source, files=tracks, is_folder_book=True),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "planned"
    assert result.is_folder_book is True
    assert result.input_paths == (source / "01.mp3", source / "02.mp3", source / "03.mp3")
    assert not any("ordering is ambiguous" in warning for warning in result.warnings)


def test_folder_book_planning_chapter_labels_use_title_then_filename(tmp_path):
    source = tmp_path / "book"
    source.mkdir()
    first = source / "01 - Opening.mp3"
    second = source / "02 - The Road.mp3"
    first.write_bytes(b"track")
    second.write_bytes(b"track")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = plan_conversion(
        make_request(
            source,
            files=(second, first),
            is_folder_book=True,
            tracks=(
                ConversionTrack(second, None, 2, None, 30),
                ConversionTrack(first, "Custom Opening", 1, None, 10),
            ),
        ),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "planned"
    assert result.chapter_titles == ("Custom Opening", "The Road")
    assert result.chapter_start_seconds == (0.0, 10.0)


def test_folder_book_planning_warns_when_ordering_is_ambiguous(tmp_path):
    source = tmp_path / "book"
    source.mkdir()
    first = source / "alpha.mp3"
    second = source / "beta.mp3"
    first.write_bytes(b"track")
    second.write_bytes(b"track")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = plan_conversion(
        make_request(source, files=(second, first), is_folder_book=True),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "planned"
    assert result.input_paths == (first, second)
    assert any("ordering is ambiguous" in warning for warning in result.warnings)


def test_missing_output_directory_is_invalid(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")
    missing_output = tmp_path / "missing"

    result = plan_conversion(
        make_request(source),
        ConversionSettings(output_dir=missing_output),
    )

    assert result.status == "invalid"
    assert any("output directory does not exist" in error for error in result.errors)
    assert result.output_path is None


def test_missing_author_or_album_is_invalid(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = plan_conversion(
        make_request(source, metadata={"title": ""}),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "invalid"
    assert any("author metadata is required" in error for error in result.errors)
    assert any("album or title metadata is required" in error for error in result.errors)
    assert result.output_path is None


def test_existing_destination_is_reported_as_conflict(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    destination = output_dir / "Author Name - Book Title.m4b"
    destination.write_bytes(b"existing")

    result = plan_conversion(
        make_request(source),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "invalid"
    assert any("destination already exists" in warning for warning in result.warnings)
    assert any("destination conflict" in error for error in result.errors)


def test_existing_archive_destination_does_not_block_plan(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / source.name).write_bytes(b"existing")

    result = plan_conversion(
        make_request(source),
        ConversionSettings(output_dir=output_dir, processed_dir=archive_dir),
    )

    assert result.status == "planned"
    assert result.archive_path == archive_dir / source.name
    assert not any("archive destination conflict" in error for error in result.errors)


def test_invalid_target_values_are_rejected_by_planner(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = plan_conversion(
        make_request(source, target_bitrate=40, target_channels=3),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "invalid"
    assert any("target bitrate must be one of" in error for error in result.errors)
    assert any("target channels must be 1 or 2" in error for error in result.errors)


def test_batch_planning_detects_intra_batch_output_conflicts(tmp_path):
    first = tmp_path / "first.mp3"
    second = tmp_path / "second.mp3"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    results = plan_conversions(
        (make_request(first), make_request(second)),
        ConversionSettings(output_dir=output_dir),
    )

    assert [result.status for result in results] == ["invalid", "invalid"]
    assert all(
        any("multiple requests target the same output path" in error for error in result.errors)
        for result in results
    )


def test_planner_performs_no_filesystem_writes(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"original source")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    before = snapshot_tree(tmp_path)

    result = plan_conversion(
        make_request(source),
        ConversionSettings(
            output_dir=output_dir,
            processed_dir=processed_dir,
            temp_dir=output_dir,
        ),
    )

    assert result.status == "planned"
    assert snapshot_tree(tmp_path) == before


def test_planner_never_launches_ffmpeg_or_subprocesses(tmp_path, monkeypatch):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fail(*args, **kwargs):
        raise AssertionError("planner attempted to launch a subprocess")

    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)

    result = plan_conversion(
        make_request(source),
        ConversionSettings(output_dir=output_dir),
    )

    assert result.status == "planned"


def snapshot_tree(root: Path) -> dict[str, tuple[bool, bytes | None]]:
    return {
        str(path.relative_to(root)): (
            path.is_dir(),
            None if path.is_dir() else path.read_bytes(),
        )
        for path in sorted(root.rglob("*"))
    }
