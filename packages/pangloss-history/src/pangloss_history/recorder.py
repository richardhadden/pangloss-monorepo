"""Putting records into the store without holding up a write.

The listener puts a record on a bounded queue and returns. One worker thread takes them in
batches and writes each batch in one transaction. If the queue is full, the record is dropped
and counted. A store that fails never fails a write. On a clean exit, what is queued is written.
"""

import atexit
import logging
import queue
import threading
import time
from collections.abc import Callable

from pangloss_history.store import HistoryRecord, HistoryStore

logger = logging.getLogger("pangloss.history")


class Recorder:
    def __init__(
        self,
        store: HistoryStore,
        queue_size: int = 1000,
        batch_size: int = 100,
        batch_ms: int = 50,
    ):
        self.store = store
        self.batch_size = batch_size
        self.batch_seconds = batch_ms / 1000
        self.queue: queue.Queue[HistoryRecord] = queue.Queue(maxsize=queue_size)
        self.dropped = 0
        self.failed = 0
        self.written = 0
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stopping = threading.Event()

    def submit(self, record: HistoryRecord) -> None:
        """Queue a record (starting the worker if it is not running). Never raises or waits"""
        self._ensure_worker()
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1
            logger.error(
                "The history queue is full: dropped %s of %s %s (%s dropped so far)",
                record.op,
                record.model,
                record.head_id,
                self.dropped,
            )

    def _ensure_worker(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stopping.clear()
                self._thread = threading.Thread(
                    target=self._work, name="pangloss-history", daemon=True
                )
                self._thread.start()

    def _next_batch(self) -> list[HistoryRecord]:
        try:
            batch = [self.queue.get(timeout=0.1)]
        except queue.Empty:
            return []
        deadline = time.monotonic() + self.batch_seconds
        while len(batch) < self.batch_size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                batch.append(self.queue.get(timeout=remaining))
            except queue.Empty:
                break
        return batch

    def _work(self) -> None:
        while not (self._stopping.is_set() and self.queue.empty()):
            batch = self._next_batch()
            if not batch:
                continue
            try:
                self.store.append(batch)
                self.written += len(batch)
            except Exception:
                self.failed += len(batch)
                logger.exception(
                    "History could not be written: %s records lost", len(batch)
                )
            finally:
                for _ in batch:
                    self.queue.task_done()

    def drain(self, timeout: float = 5.0) -> bool:
        """Wait for what is queued to be written. False if it was not done in time"""
        deadline = time.monotonic() + timeout
        while self.queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.005)
        return not self.queue.unfinished_tasks

    def stop(self, timeout: float = 5.0) -> None:
        """Write what is queued, and stop the worker"""
        self.drain(timeout)
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout)


def stop_at_exit(recorder: Recorder) -> Callable[[], None]:
    atexit.register(recorder.stop)
    return recorder.stop
