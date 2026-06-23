from pathlib import Path
import sys

import pytest


def test_package_imports_cleanly():
    import metadata_collector.alchemist_engine as engine

    assert engine.__name__ == "metadata_collector.alchemist_engine"


def test_ffmpeg_analyzer_imports():
    from metadata_collector.alchemist_engine.ffmpeg import FFmpegAnalyzer

    assert FFmpegAnalyzer.__name__ == "FFmpegAnalyzer"


def test_build_ffmpeg_command_shape():
    from metadata_collector.alchemist_engine.ffmpeg import build_ffmpeg_command

    command = build_ffmpeg_command(
        Path("/tmp/input.mp3"),
        Path("/tmp/output.m4b"),
        "libfdk_aac",
        64,
        1,
    )

    assert command[0] == "ffmpeg"
    assert "-i" in command
    assert str(Path("/tmp/input.mp3")) in command
    assert "-c:a" in command
    assert "libfdk_aac" in command
    assert "-b:a" in command
    assert "64k" in command
    assert "-ac" in command
    assert "1" in command
    assert str(Path("/tmp/output.m4b")) in command


def test_build_ffmpeg_command_maps_only_audiobook_streams():
    from metadata_collector.alchemist_engine.ffmpeg import build_ffmpeg_command

    command = build_ffmpeg_command(
        Path("/tmp/input.m4b"),
        Path("/tmp/output.m4b"),
        "libfdk_aac",
        32,
        1,
    )
    pairs = list(zip(command, command[1:]))

    assert ("-map", "0:a:0") in pairs
    assert ("-map", "0:v?") not in pairs
    assert ("-map", "0") not in pairs
    assert ("-map_chapters", "0") in pairs
    assert ("-map_metadata", "0") in pairs
    assert ("-map", "0:s?") not in pairs
    assert ("-map", "0:d?") not in pairs
    assert ("-map", "0:t?") not in pairs


def test_build_ffmpeg_command_does_not_map_artwork_in_ffmpeg_pass():
    from metadata_collector.alchemist_engine.ffmpeg import build_ffmpeg_command

    command = build_ffmpeg_command(
        Path("/tmp/input.m4b"),
        Path("/tmp/output.m4b"),
        "libfdk_aac",
        32,
        1,
    )
    pairs = list(zip(command, command[1:]))

    assert ("-map", "0:v?") not in pairs
    assert "-c:v" not in command
    assert "-disposition:v:0" not in command


def test_key_dataclasses_import_and_minimal_instantiation():
    from metadata_collector.alchemist_engine.models import AudioInfo, ConversionPlan, ProcessingStats

    audio_info = AudioInfo(
        path=Path("/tmp/input.mp3"),
        bitrate_bps=64000,
        channels=1,
        codec="mp3",
        duration_seconds=42.0,
        chapter_count=0,
    )
    plan = ConversionPlan(
        source_path=Path("/tmp/input.mp3"),
        final_path=Path("/tmp/output.m4b"),
        temporary_path=Path("/tmp/output.tmp.m4b"),
        archive_path=Path("/tmp/archive/input.mp3"),
        target_bitrate_kbps=64,
        output_channels=1,
        codec="aac",
    )
    stats = ProcessingStats(scanned=3, processed=1)

    assert audio_info.bitrate_kbps == 64
    assert audio_info.normalized_bitrate_kbps == 64
    assert plan.effective_archive_source_path == Path("/tmp/input.mp3")
    assert plan.output_channel_description == "mono"
    assert stats.remaining == 2


def test_importing_engine_does_not_import_flet():
    sys.modules.pop("flet", None)

    import metadata_collector.alchemist_engine  # noqa: F401
    import metadata_collector.alchemist_engine.ffmpeg  # noqa: F401
    import metadata_collector.alchemist_engine.models  # noqa: F401

    assert "flet" not in sys.modules


def test_missing_ffmpeg_is_reported_before_subprocess(monkeypatch, caplog):
    import subprocess

    from metadata_collector.alchemist_engine.errors import ExternalToolError
    from metadata_collector.alchemist_engine import ffmpeg

    popen_calls = []
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda executable: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: popen_calls.append(args))

    with caplog.at_level("INFO"):
        with pytest.raises(ExternalToolError) as excinfo:
            ffmpeg.run_external_command(["ffmpeg", "-hide_banner", "-encoders"])

    assert "FFmpeg executable not found" in str(excinfo.value)
    assert popen_calls == []
    assert "External command argv" in caplog.text
    assert "resolved=None" in caplog.text


def test_missing_ffprobe_has_specific_message(monkeypatch):
    from metadata_collector.alchemist_engine.errors import ExternalToolError
    from metadata_collector.alchemist_engine import ffmpeg

    monkeypatch.setattr(ffmpeg.shutil, "which", lambda executable: None)

    with pytest.raises(ExternalToolError) as excinfo:
        ffmpeg.run_external_command(["ffprobe", "-v", "error", "book.mp3"])

    assert str(excinfo.value) == (
        "FFprobe executable not found. Install FFmpeg or configure its path before converting."
    )
