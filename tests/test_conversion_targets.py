from __future__ import annotations

from pathlib import Path

from metadata_collector.conversion_queue import ConversionQueueItem, QueueStatus
from metadata_collector.conversion_queue import ConversionQueueService
from metadata_collector.conversion_runner import ConversionResult, ConversionStatus
from metadata_collector.conversion_targets import (
    apply_guessed_targets,
    apply_manual_targets,
    build_target_state,
    clone_book_with_targets,
    detects_dramatic_audio,
    format_queue_target,
    guess_targets,
    queue_item_dropdown_options,
    queue_status_color_key,
)
from metadata_collector.models import AudioFileMetadata, Book


def make_book(
    tmp_path: Path,
    *,
    key: str = "book",
    title: str = "Title",
    album: str | None = "Album",
    author: str | None = "Author",
    narrator: str | None = None,
    dramatic_audio: bool | None = None,
    target_bitrate: int | None = None,
    target_channels: int | None = None,
) -> Book:
    source = tmp_path / f"{key}.mp3"
    source.write_bytes(b"audio")
    return Book(
        key,
        str(source),
        False,
        [
            AudioFileMetadata(
                str(source),
                title=title,
                album=album,
                author=author,
                narrator=narrator,
                dramatic_audio=dramatic_audio,
                target_bitrate=target_bitrate,
                target_channels=target_channels,
            )
        ],
    )


def test_queue_item_dropdown_options_use_title_for_display(tmp_path):
    item = ConversionQueueItem(
        queue_id="queue-guid",
        book_key="book",
        display_title="The Book Title",
        source_path=tmp_path / "book.mp3",
        output_path=None,
        book_type="single-file",
        status=QueueStatus.READY,
    )

    assert queue_item_dropdown_options([item]) == [("queue-guid", "The Book Title")]


def test_target_prefill_and_manual_override(tmp_path):
    book = make_book(tmp_path, target_bitrate=64, target_channels=1)
    state = build_target_state(
        book,
        bitrate_reader=lambda _: 128,
        channel_reader=lambda _: 2,
    )

    assert state.target_bitrate == 64
    assert state.target_channels == 1
    assert state.reason == "Manual target"

    updated = apply_manual_targets(state, 96, 2)

    assert updated.target_bitrate == 96
    assert updated.target_channels == 2
    assert updated.reason == "Manual target"


def test_set_all_targets_behavior_updates_selected_state(tmp_path):
    state = build_target_state(
        make_book(tmp_path),
        bitrate_reader=lambda _: 128,
        channel_reader=lambda _: 2,
    )

    updated = apply_manual_targets(state, 48, 1)

    assert updated.target_bitrate == 48
    assert updated.target_channels == 1
    assert updated.reason == "Manual target"


def test_dramatic_audio_detection_uses_flag_and_text_markers(tmp_path):
    assert detects_dramatic_audio(make_book(tmp_path, key="flag", dramatic_audio=True))
    assert detects_dramatic_audio(make_book(tmp_path, key="album", album="Graphic Audio Presents"))
    assert detects_dramatic_audio(make_book(tmp_path, key="title", title="A Dramatic Reading"))
    assert detects_dramatic_audio(make_book(tmp_path, key="narrator", narrator="DramaticAudio Cast"))
    assert not detects_dramatic_audio(make_book(tmp_path, key="plain", title="Plain Reading"))


def test_guess_target_rules():
    assert guess_targets(128, 2, dramatic_audio=False).target_bitrate == 64
    assert guess_targets(100, 2, dramatic_audio=False).target_bitrate == 48
    assert guess_targets(80, 2, dramatic_audio=False).target_bitrate == 32
    assert guess_targets(64, 1, dramatic_audio=False).target_bitrate == 64
    assert guess_targets(48, 1, dramatic_audio=False).target_bitrate == 48
    assert guess_targets(40, 1, dramatic_audio=False).target_bitrate == 32
    assert guess_targets(256, 2, dramatic_audio=True).target_bitrate == 128
    assert guess_targets(96, 1, dramatic_audio=True).target_channels == 2
    assert guess_targets(128, 2, dramatic_audio=False).reason == "Stereo source -> 64 kbps mono"
    assert guess_targets(64, 1, dramatic_audio=False).reason == "Mono source -> 64 kbps mono"
    assert guess_targets(256, 2, dramatic_audio=True).reason == "Detected dramatic audio"
    assert guess_targets(None, 2, dramatic_audio=False).reason == "Missing source bitrate"
    assert guess_targets(64, None, dramatic_audio=False).reason == "Missing source channels"


def test_apply_guessed_targets_updates_state(tmp_path):
    state = build_target_state(
        make_book(tmp_path, album="Graphic Audio Adventure"),
        bitrate_reader=lambda _: 96,
        channel_reader=lambda _: 2,
    )

    guessed = apply_guessed_targets(state)

    assert guessed.target_bitrate == 64
    assert guessed.target_channels == 2
    assert guessed.reason == "Detected dramatic audio"


def test_queue_request_integration_uses_selected_targets(tmp_path):
    book = make_book(tmp_path, target_bitrate=64, target_channels=1)
    queued_book = clone_book_with_targets(book, 96, 2)
    captured = []

    class CapturingRunner:
        def run(self, request, progress_callback=None):
            captured.append((request.target_bitrate, request.target_channels))
            return ConversionResult(ConversionStatus.SUCCESS, "ok", request.source_path)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    service = ConversionQueueService(runner_factory=lambda prepared: CapturingRunner())
    service.add_books(
        [queued_book],
        {"conversion_output_dir": str(output_dir), "archive_dir": str(tmp_path / "archive")},
    )
    service.run_pending()

    assert queued_book.files[0].target_bitrate == 96
    assert queued_book.files[0].target_channels == 2
    assert book.files[0].target_bitrate == 64
    assert book.files[0].target_channels == 1
    assert captured == [(96, 2)]


def test_status_to_color_mapping():
    assert queue_status_color_key(QueueStatus.READY) == "light_blue"
    assert queue_status_color_key(QueueStatus.CONVERTING) == "dark_blue"
    assert queue_status_color_key(QueueStatus.WRITING_METADATA) == "dark_blue"
    assert queue_status_color_key(QueueStatus.COMPLETE) == "light_green"
    assert queue_status_color_key(QueueStatus.FAILED) == "red"
    assert queue_status_color_key(QueueStatus.CANCELLED) == "gray"


def test_format_queue_target_uses_request_and_plan_values(tmp_path):
    service = ConversionQueueService()
    item = service.add_books(
        [make_book(tmp_path, target_bitrate=64, target_channels=1)],
        {"conversion_output_dir": str(tmp_path), "archive_dir": str(tmp_path / "archive")},
    )[0]

    assert format_queue_target(item) == "64/mono"

    stereo = service.add_books(
        [make_book(tmp_path, key="stereo", target_bitrate=128, target_channels=2)],
        {"conversion_output_dir": str(tmp_path), "archive_dir": str(tmp_path / "archive")},
    )[0]

    assert format_queue_target(stereo) == "128/stereo"

    unknown = ConversionQueueItem(
        queue_id="missing",
        book_key="missing",
        display_title="Missing",
        source_path=tmp_path / "missing.mp3",
        output_path=None,
        book_type="single-file",
        status=QueueStatus.FAILED,
    )

    assert format_queue_target(unknown) == "Unknown"


def test_start_queue_dialog_is_wired_in_app_source():
    source = Path("metadata_collector/app.py").read_text()

    assert "title=ft.Text('Queue Started')" in source
    assert "The conversion queue is now running in the background." in source
    assert "Return to Main" in source
    assert "Stay Here" in source


def test_queue_table_uses_fixed_row_heights_instead_of_stretch_layout():
    source = Path("metadata_collector/app.py").read_text()

    assert "queue_row_height=64" in source
    assert "queue_header_height=48" in source
    assert "queue_header=ft.Container" in source
    assert "queue_rows=ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)" in source
    assert "queue_rows_container=ft.Container" in source
    assert "content=queue_rows,\n            height=320" not in source
    assert "content=queue_rows,\n            width=queue_table_width,\n            expand=True" in source
    assert "clip_behavior=ft.ClipBehavior.HARD_EDGE" in source
    assert "queue_rows.height=" not in source
    assert "CrossAxisAlignment.STRETCH" not in source


def test_queue_table_includes_target_column():
    source = Path("metadata_collector/app.py").read_text()

    assert "ft.Text('Target', weight=ft.FontWeight.BOLD)" in source
    assert "queue_cell(format_queue_target(item), 110" in source
    assert "queue_rows_container" in source


def test_conversion_queue_layout_uses_expandable_root_and_queue_section():
    source = Path("metadata_collector/app.py").read_text()

    assert "books_container=ft.Container(content=book_rows, height=220" in source
    assert "queue_section=ft.Column(" in source
    assert "queue_rows_container," in source
    assert "conversion_queue_screen=ft.Column(" in source
    assert "expand=True,\n            spacing=8" in source
    assert "replace_page_controls(\n            conversion_queue_screen," in source


def test_queue_screen_syncs_rows_dropdown_and_pending_target_edits():
    source = Path("metadata_collector/app.py").read_text()

    assert "items_by_book_key={item.book_key: item for item in items}" in source
    assert "queue_item_dropdown_options(removable)" in source
    assert "checkbox.value=True" in source
    assert "checkbox.disabled=True" in source
    assert "checkbox.value=False" in source
    assert "elif item.status in {QueueStatus.FAILED, QueueStatus.CANCELLED}:" in source
    assert "editable=item.status in PENDING_STATUSES" in source
    assert "conversion_queue.update_book(queued_book_for_state(book_key), settings)" in source


def test_duplicate_add_flow_continues_after_dialog_choice():
    source = Path("metadata_collector/app.py").read_text()

    assert "def process_add_books(chosen, index=0, summary=None):" in source
    assert "continue_add=lambda: process_add_books(chosen, index + 1, summary)" in source
    assert "show_duplicate_dialog(book, existing, continue_add, summary)" in source
    assert "summary.__setitem__('replaced', summary['replaced'] + 1)" in source
