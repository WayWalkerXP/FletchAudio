from __future__ import annotations

import threading
import time
from pathlib import Path

from metadata_collector.conversion_adapter import ConversionRequest, ConversionSettings, ConversionTrack
from metadata_collector.conversion_planner import plan_conversion
from metadata_collector.conversion_queue import ConversionQueueService, QueueStatus
from metadata_collector.conversion_runner import ConversionProgressEvent, ConversionResult, ConversionStatus
from metadata_collector.conversion_ui import PreparedConversion


def make_request(tmp_path: Path, key: str, *, folder: bool = False, bitrate: int | None = 64) -> ConversionRequest:
    if folder:
        source = tmp_path / key
        source.mkdir(parents=True)
        first = source / "01.mp3"
        second = source / "02.mp3"
        first.write_bytes(b"one")
        second.write_bytes(b"two")
        files = (first, second)
        tracks = (
            ConversionTrack(first, "One", 1, None, 10),
            ConversionTrack(second, "Two", 2, None, 10),
        )
    else:
        source = tmp_path / f"{key}.mp3"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"audio")
        files = (source,)
        tracks = ()
    return ConversionRequest(
        book_key=key,
        source_path=source,
        is_folder_book=folder,
        files=files,
        target_bitrate=bitrate,
        target_channels=1,
        dramatic_audio=False,
        metadata={"title": f"Title {key}", "author": "Author"},
        tracks=tracks,
    )


def make_prepared(tmp_path: Path, key: str, *, folder: bool = False, bitrate: int | None = 64) -> PreparedConversion:
    request = make_request(tmp_path, key, folder=folder, bitrate=bitrate)
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    settings = ConversionSettings(output_dir=output_dir, processed_dir=tmp_path / "archive")
    return PreparedConversion(request=request, settings=settings, plan=plan_conversion(request, settings))


class FakeRunner:
    def __init__(self, outcome: ConversionStatus = ConversionStatus.SUCCESS, *, events=None, delay: float = 0.0):
        self.outcome = outcome
        self.events = list(events or [])
        self.delay = delay
        self.calls: list[str] = []

    def run(self, request, progress_callback=None):
        self.calls.append(request.book_key)
        for event in self.events:
            progress_callback(event)
        if self.delay:
            time.sleep(self.delay)
        return ConversionResult(
            status=self.outcome,
            message="ok" if self.outcome == ConversionStatus.SUCCESS else "failed",
            source_path=request.source_path,
            final_output_path=Path("out") / f"{request.book_key}.m4b",
            error_details=None if self.outcome == ConversionStatus.SUCCESS else "boom",
        )


def test_queue_accepts_valid_single_file_and_folder_book_items(tmp_path):
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner())

    items = service.add_prepared(
        [
            ("Single", make_prepared(tmp_path, "single")),
            ("Folder", make_prepared(tmp_path, "folder", folder=True)),
        ]
    )

    assert [item.status for item in items] == [QueueStatus.READY, QueueStatus.READY]
    assert [item.book_type for item in items] == ["single-file", "folder-book"]
    assert all(item.output_path is not None for item in items)


def test_duplicate_book_key_is_not_added_twice(tmp_path):
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner())
    first = make_prepared(tmp_path, "same")
    duplicate = make_prepared(tmp_path, "same")

    items = service.add_prepared([("First", first), ("Duplicate", duplicate)])

    assert len(service.snapshot()) == 1
    assert items[0] is items[1]
    assert service.find_by_book_key("same") is items[0]


def test_book_key_lookup_and_update_keep_queue_consistent(tmp_path):
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner())
    item = service.add_prepared([("Book", make_prepared(tmp_path, "book", bitrate=64))])[0]
    updated = make_prepared(tmp_path, "book", bitrate=96)
    replacement = service.replace_item(item.queue_id, service._item_from_prepared("Book", updated))

    assert replacement.queue_id == item.queue_id
    assert service.find_by_book_key("book").request.target_bitrate == 96
    assert len(service.snapshot()) == 1


def test_replace_item_allows_failed_or_cancelled_but_not_active_or_complete(tmp_path):
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner())
    item = service.add_prepared([("Book", make_prepared(tmp_path, "book"))])[0]
    replacement = service._item_from_prepared("Book", make_prepared(tmp_path, "book", bitrate=96))

    item.status = QueueStatus.FAILED
    assert service.replace_item(item.queue_id, replacement) is not None
    assert service.find_by_book_key("book").request.target_bitrate == 96

    item = service.find_by_book_key("book")
    item.status = QueueStatus.CANCELLED
    replacement = service._item_from_prepared("Book", make_prepared(tmp_path, "book", bitrate=128))
    assert service.replace_item(item.queue_id, replacement) is not None
    assert service.find_by_book_key("book").request.target_bitrate == 128

    item = service.find_by_book_key("book")
    item.status = QueueStatus.CONVERTING
    replacement = service._item_from_prepared("Book", make_prepared(tmp_path, "book", bitrate=256))
    assert service.replace_item(item.queue_id, replacement) is None
    assert service.find_by_book_key("book").request.target_bitrate == 128

    item.status = QueueStatus.COMPLETE
    assert service.replace_item(item.queue_id, replacement) is None
    assert service.find_by_book_key("book").request.target_bitrate == 128


def test_invalid_plan_is_marked_failed_before_execution(tmp_path):
    runner = FakeRunner()
    service = ConversionQueueService(runner_factory=lambda prepared: runner)
    invalid = make_prepared(tmp_path, "bad", bitrate=None)

    item = service.add_prepared([("Bad", invalid)])[0]
    service.run_pending()

    assert item.status == QueueStatus.FAILED
    assert "target bitrate" in item.error_text
    assert runner.calls == []


def test_items_process_sequentially(tmp_path):
    order = []

    class OrderedRunner:
        def __init__(self, prepared):
            self.prepared = prepared

        def run(self, request, progress_callback=None):
            order.append(("start", request.book_key))
            time.sleep(0.01)
            order.append(("finish", request.book_key))
            return ConversionResult(ConversionStatus.SUCCESS, "ok", request.source_path)

    service = ConversionQueueService(runner_factory=OrderedRunner)
    service.add_prepared(
        [
            ("One", make_prepared(tmp_path, "one")),
            ("Two", make_prepared(tmp_path, "two")),
        ]
    )

    service.run_pending()

    assert order == [("start", "one"), ("finish", "one"), ("start", "two"), ("finish", "two")]


def test_failure_of_one_item_does_not_prevent_later_items(tmp_path):
    outcomes = {
        "one": ConversionStatus.FAILED,
        "two": ConversionStatus.SUCCESS,
    }

    service = ConversionQueueService(
        runner_factory=lambda prepared: FakeRunner(outcomes[prepared.request.book_key])
    )
    items = service.add_prepared(
        [
            ("One", make_prepared(tmp_path, "one")),
            ("Two", make_prepared(tmp_path, "two")),
        ]
    )

    service.run_pending()

    assert items[0].status == QueueStatus.FAILED
    assert items[1].status == QueueStatus.COMPLETE


def test_queued_item_removal_works_before_start(tmp_path):
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner())
    item = service.add_prepared([("One", make_prepared(tmp_path, "one"))])[0]

    assert service.remove_queued(item.queue_id) is True

    assert service.snapshot() == []


def test_cancelling_queued_item_marks_it_cancelled(tmp_path):
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner())
    item = service.add_prepared([("One", make_prepared(tmp_path, "one"))])[0]

    assert service.cancel(item.queue_id) is True

    assert item.status == QueueStatus.CANCELLED
    assert "before it started" in item.message


def test_cancelling_active_item_invokes_safe_path_and_does_not_archive_source(tmp_path):
    cancel_called = threading.Event()
    release_runner = threading.Event()
    source_archived = []

    class BlockingRunner:
        def run(self, request, progress_callback=None):
            progress_callback(
                ConversionProgressEvent("converting", "Converting audio", request.source_path)
            )
            release_runner.wait(2)
            source_archived.append(False)
            return ConversionResult(
                ConversionStatus.FAILED,
                "Conversion failed",
                request.source_path,
                error_details="cancelled",
            )

    service = ConversionQueueService(
        runner_factory=lambda prepared: BlockingRunner(),
        cancel_active_processes=lambda: (cancel_called.set(), release_runner.set()),
    )
    item = service.add_prepared([("One", make_prepared(tmp_path, "one"))])[0]
    worker = threading.Thread(target=service.run_pending)
    worker.start()
    time.sleep(0.05)

    assert service.cancel_current() is True
    worker.join(2)

    assert cancel_called.is_set()
    assert item.status == QueueStatus.CANCELLED
    assert item.source_path.exists()
    assert source_archived == [False]


def test_progress_events_update_queue_item_status_stage_and_message(tmp_path):
    event = ConversionProgressEvent(
        "writing_metadata",
        "Writing audiobook metadata",
        tmp_path / "one.mp3",
        final_output_path=tmp_path / "out.m4b",
    )
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner(events=[event]))
    item = service.add_prepared([("One", make_prepared(tmp_path, "one"))])[0]

    service.run_pending()

    assert item.status == QueueStatus.COMPLETE
    assert item.current_stage == "complete"
    assert item.message == "ok"
    assert item.output_path == Path("out") / "one.m4b"

    seen = []
    service = ConversionQueueService(runner_factory=lambda prepared: FakeRunner(events=[event]))
    service.subscribe(lambda updated: seen.append((updated.status, updated.current_stage, updated.message)))
    service.add_prepared([("Two", make_prepared(tmp_path, "two"))])
    service.run_pending()

    assert (QueueStatus.WRITING_METADATA, "writing_metadata", "Writing audiobook metadata") in seen
