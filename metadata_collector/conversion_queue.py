"""In-memory conversion queue orchestration.

Queue state is intentionally process-local for FA-CONV-0007. Closing the app
clears pending and completed queue items.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol

from .alchemist_engine.ffmpeg import terminate_active_external_processes
from .conversion_adapter import ConversionRequest
from .conversion_runner import (
    ConversionProgressEvent,
    ConversionResult,
    ConversionRunner,
    ConversionStatus,
)
from .conversion_ui import ConversionUiError, PreparedConversion, prepare_conversion
from .models import Book


class QueueStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    READY = "ready"
    CONVERTING = "converting"
    VALIDATING = "validating"
    WRITING_METADATA = "writing_metadata"
    PROMOTING = "promoting"
    ARCHIVING = "archiving"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    QueueStatus.COMPLETE,
    QueueStatus.FAILED,
    QueueStatus.CANCELLED,
}
PENDING_STATUSES = {
    QueueStatus.QUEUED,
    QueueStatus.PLANNING,
    QueueStatus.READY,
}
ACTIVE_STATUSES = {
    QueueStatus.CONVERTING,
    QueueStatus.VALIDATING,
    QueueStatus.WRITING_METADATA,
    QueueStatus.PROMOTING,
    QueueStatus.ARCHIVING,
}


@dataclass
class ConversionQueueItem:
    queue_id: str
    book_key: str
    display_title: str
    source_path: Path
    output_path: Path | None
    book_type: str
    status: QueueStatus
    current_stage: str = ""
    message: str = ""
    error_text: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    request: ConversionRequest | None = field(default=None, repr=False)
    prepared: PreparedConversion | None = field(default=None, repr=False)
    cancellation_requested: bool = False


class QueueRunner(Protocol):
    def run(
        self,
        request: ConversionRequest,
        progress_callback: Callable[[ConversionProgressEvent], None] | None = None,
    ) -> ConversionResult: ...


RunnerFactory = Callable[[PreparedConversion], QueueRunner]
QueueObserver = Callable[[ConversionQueueItem], None]


class ConversionQueueService:
    """Sequential in-memory queue for planned audiobook conversions."""

    def __init__(
        self,
        *,
        runner_factory: RunnerFactory | None = None,
        cancel_active_processes: Callable[[], None] = terminate_active_external_processes,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._runner_factory = runner_factory or (lambda prepared: ConversionRunner(prepared.settings))
        self._cancel_active_processes = cancel_active_processes
        self._clock = clock
        self._items: list[ConversionQueueItem] = []
        self._lock = threading.RLock()
        self._active_queue_id: str | None = None
        self._observers: list[QueueObserver] = []
        self._running = False

    def subscribe(self, observer: QueueObserver) -> None:
        with self._lock:
            self._observers.append(observer)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def snapshot(self) -> list[ConversionQueueItem]:
        with self._lock:
            return list(self._items)

    def find_by_book_key(self, book_key: str) -> ConversionQueueItem | None:
        with self._lock:
            return self._find_by_book_key(book_key)

    def book_keys(self) -> set[str]:
        with self._lock:
            return {item.book_key for item in self._items}

    def add_books(
        self,
        books: Iterable[Book],
        app_settings: Mapping[str, object],
    ) -> list[ConversionQueueItem]:
        items: list[ConversionQueueItem] = []
        for book in books:
            try:
                prepared = prepare_conversion(book, app_settings)
            except ConversionUiError as exc:
                item = self._failed_item_from_book(book, str(exc))
            else:
                item = self._item_from_prepared(book.display_name, prepared)
            item = self._append_unique_item(item)
            items.append(item)
        return items

    def add_prepared(
        self,
        prepared_items: Iterable[tuple[str, PreparedConversion]],
    ) -> list[ConversionQueueItem]:
        items = [self._item_from_prepared(title, prepared) for title, prepared in prepared_items]
        return [self._append_unique_item(item) for item in items]

    def update_book(
        self,
        book: Book,
        app_settings: Mapping[str, object],
    ) -> ConversionQueueItem | None:
        existing = self.find_by_book_key(str(getattr(book, "key", "")))
        if existing is None or existing.status not in PENDING_STATUSES:
            return None
        try:
            prepared = prepare_conversion(book, app_settings)
        except ConversionUiError as exc:
            item = self._failed_item_from_book(book, str(exc))
        else:
            item = self._item_from_prepared(book.display_name, prepared)
        return self.replace_item(existing.queue_id, item)

    def replace_book(
        self,
        book: Book,
        app_settings: Mapping[str, object],
    ) -> ConversionQueueItem | None:
        existing = self.find_by_book_key(str(getattr(book, "key", "")))
        if existing is None or existing.status not in {QueueStatus.FAILED, QueueStatus.CANCELLED}:
            return None
        try:
            prepared = prepare_conversion(book, app_settings)
        except ConversionUiError as exc:
            item = self._failed_item_from_book(book, str(exc))
        else:
            item = self._item_from_prepared(book.display_name, prepared)
        return self.replace_item(existing.queue_id, item)

    def replace_item(self, queue_id: str, replacement: ConversionQueueItem) -> ConversionQueueItem | None:
        with self._lock:
            for index, item in enumerate(self._items):
                if item.queue_id != queue_id or item.status in ACTIVE_STATUSES or item.status == QueueStatus.COMPLETE:
                    continue
                replacement.queue_id = item.queue_id
                replacement.created_at = item.created_at
                replacement.updated_at = self._clock()
                self._items[index] = replacement
                self._notify(replacement)
                return replacement
        return None

    def remove_queued(self, queue_id: str) -> bool:
        with self._lock:
            for index, item in enumerate(self._items):
                if item.queue_id == queue_id and item.status in {QueueStatus.QUEUED, QueueStatus.READY}:
                    item = self._items.pop(index)
                    self._notify(item)
                    return True
        return False

    def cancel(self, queue_id: str) -> bool:
        with self._lock:
            item = self._find(queue_id)
            if item is None or item.status in TERMINAL_STATUSES:
                return False
            item.cancellation_requested = True
            if item.queue_id == self._active_queue_id:
                item.message = "Cancellation requested; stopping active conversion"
                item.updated_at = self._clock()
                self._notify(item)
                self._cancel_active_processes()
                return True
            item.status = QueueStatus.CANCELLED
            item.current_stage = QueueStatus.CANCELLED.value
            item.message = "Conversion cancelled before it started"
            item.finished_at = self._clock()
            item.updated_at = item.finished_at
            self._notify(item)
            return True

    def cancel_current(self) -> bool:
        with self._lock:
            active_id = self._active_queue_id
        return self.cancel(active_id) if active_id else False

    def clear_terminal(self) -> int:
        with self._lock:
            before = len(self._items)
            self._items = [item for item in self._items if item.status not in TERMINAL_STATUSES]
            removed = before - len(self._items)
        if removed:
            self._notify_all()
        return removed

    def run_pending(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        try:
            while True:
                item = self._next_runnable_item()
                if item is None:
                    return
                self._run_item(item)
        finally:
            with self._lock:
                self._running = False
                self._active_queue_id = None
            self._notify_all()

    def _run_item(self, item: ConversionQueueItem) -> None:
        prepared = item.prepared
        request = item.request
        if prepared is None or request is None:
            self._mark_failed(item, "Conversion request is unavailable")
            return
        with self._lock:
            if item.cancellation_requested or item.status == QueueStatus.CANCELLED:
                item.status = QueueStatus.CANCELLED
                item.current_stage = QueueStatus.CANCELLED.value
                item.message = "Conversion cancelled before it started"
                item.finished_at = self._clock()
                item.updated_at = item.finished_at
                self._notify(item)
                return
            self._active_queue_id = item.queue_id
            item.status = QueueStatus.CONVERTING
            item.current_stage = QueueStatus.CONVERTING.value
            item.message = "Starting conversion"
            item.started_at = self._clock()
            item.updated_at = item.started_at
            self._notify(item)

        runner = self._runner_factory(prepared)
        try:
            result = runner.run(request, lambda event: self._handle_progress(item.queue_id, event))
        except Exception as exc:
            if item.cancellation_requested:
                self._mark_cancelled(item, "Conversion cancelled")
            else:
                self._mark_failed(item, f"Conversion failed: {exc}")
            return
        finally:
            with self._lock:
                if self._active_queue_id == item.queue_id:
                    self._active_queue_id = None

        with self._lock:
            if item.cancellation_requested:
                item.status = QueueStatus.CANCELLED
                item.current_stage = QueueStatus.CANCELLED.value
                item.message = "Conversion cancelled"
                item.error_text = None
            elif result.status == ConversionStatus.SUCCESS:
                item.status = QueueStatus.COMPLETE
                item.current_stage = QueueStatus.COMPLETE.value
                item.message = result.message
                item.output_path = result.final_output_path or item.output_path
                item.error_text = result.error_details
            else:
                item.status = QueueStatus.FAILED
                item.current_stage = QueueStatus.FAILED.value
                item.message = result.message
                item.error_text = result.error_details or result.message
                item.output_path = result.final_output_path or item.output_path
            item.finished_at = self._clock()
            item.updated_at = item.finished_at
            self._notify(item)

    def _handle_progress(self, queue_id: str, event: ConversionProgressEvent) -> None:
        with self._lock:
            item = self._find(queue_id)
            if item is None or item.status in TERMINAL_STATUSES:
                return
            status = _status_for_stage(event.stage)
            if status is not None:
                item.status = status
            item.current_stage = event.stage
            item.message = event.message
            item.output_path = event.final_output_path or item.output_path
            item.updated_at = self._clock()
            self._notify(item)

    def _next_runnable_item(self) -> ConversionQueueItem | None:
        with self._lock:
            for item in self._items:
                if item.status in {QueueStatus.QUEUED, QueueStatus.READY}:
                    return item
        return None

    def _item_from_prepared(self, title: str, prepared: PreparedConversion) -> ConversionQueueItem:
        plan = prepared.plan
        item = ConversionQueueItem(
            queue_id=str(uuid.uuid4()),
            book_key=prepared.request.book_key,
            display_title=title,
            source_path=prepared.request.source_path,
            output_path=plan.output_path,
            book_type="folder-book" if prepared.request.is_folder_book else "single-file",
            status=QueueStatus.READY if plan.status == "planned" else QueueStatus.FAILED,
            current_stage=QueueStatus.READY.value if plan.status == "planned" else QueueStatus.FAILED.value,
            message="Ready to convert" if plan.status == "planned" else "Conversion plan is invalid",
            error_text="; ".join(plan.errors) or None,
            request=prepared.request if plan.status == "planned" else None,
            prepared=prepared if plan.status == "planned" else None,
        )
        if plan.status != "planned":
            item.finished_at = item.created_at
        return item

    def _failed_item_from_book(self, book: Book, message: str) -> ConversionQueueItem:
        now = self._clock()
        return ConversionQueueItem(
            queue_id=str(uuid.uuid4()),
            book_key=str(getattr(book, "key", "")),
            display_title=book.display_name,
            source_path=Path(str(getattr(book, "path", ""))),
            output_path=None,
            book_type="folder-book" if getattr(book, "is_folder_book", False) else "single-file",
            status=QueueStatus.FAILED,
            current_stage=QueueStatus.FAILED.value,
            message="Conversion plan is invalid",
            error_text=message,
            created_at=now,
            updated_at=now,
            finished_at=now,
        )

    def _mark_cancelled(self, item: ConversionQueueItem, message: str) -> None:
        with self._lock:
            item.status = QueueStatus.CANCELLED
            item.current_stage = QueueStatus.CANCELLED.value
            item.message = message
            item.error_text = None
            item.finished_at = self._clock()
            item.updated_at = item.finished_at
            self._notify(item)

    def _mark_failed(self, item: ConversionQueueItem, message: str) -> None:
        with self._lock:
            item.status = QueueStatus.FAILED
            item.current_stage = QueueStatus.FAILED.value
            item.message = message
            item.error_text = message
            item.finished_at = self._clock()
            item.updated_at = item.finished_at
            self._notify(item)

    def _append_item(self, item: ConversionQueueItem) -> None:
        with self._lock:
            self._items.append(item)
            self._notify(item)

    def _append_unique_item(self, item: ConversionQueueItem) -> ConversionQueueItem:
        with self._lock:
            existing = self._find_by_book_key(item.book_key)
            if existing is not None:
                return existing
            self._items.append(item)
            self._notify(item)
            return item

    def _find(self, queue_id: str | None) -> ConversionQueueItem | None:
        if queue_id is None:
            return None
        for item in self._items:
            if item.queue_id == queue_id:
                return item
        return None

    def _find_by_book_key(self, book_key: str | None) -> ConversionQueueItem | None:
        if book_key is None:
            return None
        for item in self._items:
            if item.book_key == book_key:
                return item
        return None

    def _notify(self, item: ConversionQueueItem) -> None:
        observers = list(self._observers)
        for observer in observers:
            try:
                observer(item)
            except Exception:
                pass

    def _notify_all(self) -> None:
        observers = list(self._observers)
        items = list(self._items)
        for item in items:
            for observer in observers:
                try:
                    observer(item)
                except Exception:
                    pass


def _status_for_stage(stage: str) -> QueueStatus | None:
    normalized = str(stage).strip().lower()
    if normalized == "probing":
        return QueueStatus.PLANNING
    try:
        return QueueStatus(normalized)
    except ValueError:
        return None
