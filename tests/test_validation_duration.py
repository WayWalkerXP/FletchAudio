from __future__ import annotations

import json
from pathlib import Path

from metadata_collector.alchemist_engine import ffmpeg
from metadata_collector.alchemist_engine.ffmpeg import CommandResult, FFmpegAnalyzer
from metadata_collector.alchemist_engine.models import AudioInfo, ConversionPlan
from metadata_collector.alchemist_engine.validation import ValidationManager


def _probe_result(data: dict) -> CommandResult:
    return CommandResult(["ffprobe"], 0, json.dumps(data), "")


def _ffprobe_data(*, audio_duration: str | None, video_duration: str = "0.33", format_duration: str = "0.33") -> dict:
    audio_stream = {
        "index": 0,
        "codec_type": "audio",
        "codec_name": "aac",
        "bit_rate": "64000",
        "channels": 1,
    }
    if audio_duration is not None:
        audio_stream["duration"] = audio_duration
    return {
        "streams": [
            audio_stream,
            {
                "index": 1,
                "codec_type": "video",
                "codec_name": "mjpeg",
                "duration": video_duration,
                "disposition": {"attached_pic": 1},
                "tags": {"title": "cover"},
            },
        ],
        "format": {"duration": format_duration, "bit_rate": "64000", "tags": {"title": "Book"}},
        "chapters": [{"id": 0}],
    }


def test_probe_prefers_primary_audio_duration_over_misleading_format_and_artwork(monkeypatch):
    monkeypatch.setattr(
        ffmpeg,
        "run_external_command",
        lambda command: _probe_result(_ffprobe_data(audio_duration="40008.26")),
    )

    info = FFmpegAnalyzer().probe(Path("book.m4b"))

    assert info.duration_seconds == 40008.26
    assert info.audio_duration_seconds == 40008.26
    assert info.format_duration_seconds == 0.33
    assert info.duration_source == "audio"


def test_probe_ignores_attached_picture_duration(monkeypatch):
    monkeypatch.setattr(
        ffmpeg,
        "run_external_command",
        lambda command: _probe_result(_ffprobe_data(audio_duration="40008.26", video_duration="0.33")),
    )

    info = FFmpegAnalyzer().probe(Path("book-with-cover.m4b"))

    assert info.duration_seconds == 40008.26
    assert any("attached_pic=1" in stream for stream in info.stream_summary)
    assert all("duration=0.33" not in stream or "type=video" in stream for stream in info.stream_summary)


def test_probe_falls_back_to_format_duration_when_audio_duration_is_missing(monkeypatch, caplog):
    monkeypatch.setattr(
        ffmpeg,
        "run_external_command",
        lambda command: _probe_result(_ffprobe_data(audio_duration=None, format_duration="123.45")),
    )

    with caplog.at_level("WARNING"):
        info = FFmpegAnalyzer().probe(Path("legacy-book.m4b"))

    assert info.duration_seconds == 123.45
    assert info.audio_duration_seconds is None
    assert info.format_duration_seconds == 123.45
    assert info.duration_source == "format"
    assert "falling back to format duration" in caplog.text


class FakeValidationAnalyzer:
    def __init__(self, output_info: AudioInfo) -> None:
        self.output_info = output_info

    def probe(self, path: Path) -> AudioInfo:
        return self.output_info


def _audio_info(
    path: Path,
    *,
    duration: float,
    audio_duration: float,
    format_duration: float,
    chapters: int = 1,
) -> AudioInfo:
    return AudioInfo(
        path=path,
        bitrate_bps=64_000,
        channels=1,
        codec="aac",
        duration_seconds=duration,
        chapter_count=chapters,
        audio_duration_seconds=audio_duration,
        format_duration_seconds=format_duration,
        duration_source="audio",
        stream_summary=(
            f"index=0 type=audio codec=aac duration={audio_duration} attached_pic=0",
            f"index=1 type=video codec=mjpeg duration={format_duration} attached_pic=1",
        ),
    )


def _plan(tmp_path: Path) -> ConversionPlan:
    return ConversionPlan(
        source_path=tmp_path / "source.m4b",
        final_path=tmp_path / "output.m4b",
        temporary_path=tmp_path / "output.tmp.m4b",
        archive_path=tmp_path / "source.m4b",
        target_bitrate_kbps=64,
        output_channels=1,
        codec="aac",
    )


def test_validation_succeeds_when_audio_durations_match_despite_misleading_format_duration(tmp_path, caplog):
    output_path = tmp_path / "output.m4b"
    output_path.write_bytes(b"converted")
    source_info = _audio_info(tmp_path / "source.m4b", duration=40008.26, audio_duration=40008.26, format_duration=40008.26)
    output_info = _audio_info(output_path, duration=40008.4, audio_duration=40008.4, format_duration=0.33)

    with caplog.at_level("INFO"):
        valid = ValidationManager(FakeValidationAnalyzer(output_info)).validate(source_info, _plan(tmp_path), output_path)

    assert valid is True
    assert "output_audio_duration=40008.4" in caplog.text
    assert "output_format_duration=0.33" in caplog.text
    assert "output_duration_source=audio" in caplog.text


def test_validation_still_fails_when_audio_durations_differ(tmp_path):
    output_path = tmp_path / "output.m4b"
    output_path.write_bytes(b"converted")
    source_info = _audio_info(tmp_path / "source.m4b", duration=40008.26, audio_duration=40008.26, format_duration=40008.26)
    output_info = _audio_info(output_path, duration=12.0, audio_duration=12.0, format_duration=0.33)

    valid = ValidationManager(FakeValidationAnalyzer(output_info)).validate(source_info, _plan(tmp_path), output_path)

    assert valid is False
