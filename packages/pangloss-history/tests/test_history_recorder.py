import threading
from uuid import uuid7

from history_support import record
from pangloss_history.recorder import Recorder


class ListStore:
    def __init__(self):
        self.batches = []
        self.fail = False
        self.gate = threading.Event()
        self.gate.set()

    def append(self, records):
        self.gate.wait()
        if self.fail:
            raise OSError("disk full")
        self.batches.append(list(records))


def test_records_are_written_in_the_order_they_were_given():
    store = ListStore()
    recorder = Recorder(store, batch_ms=20)
    records = [record(uuid7(), 1) for _ in range(10)]
    for r in records:
        recorder.submit(r)
    assert recorder.drain()
    assert [r for batch in store.batches for r in batch] == records
    assert recorder.written == 10
    recorder.stop()


def test_records_that_come_together_are_written_together():
    store = ListStore()
    recorder = Recorder(store, batch_size=100, batch_ms=200)
    for _ in range(30):
        recorder.submit(record())
    recorder.drain()
    assert sum(len(b) for b in store.batches) == 30
    assert len(store.batches) < 30
    recorder.stop()


def test_a_full_queue_drops_and_counts_and_does_not_wait():
    store = ListStore()
    store.gate.clear()  # (the worker is stuck writing)
    recorder = Recorder(store, queue_size=2, batch_size=1, batch_ms=1)
    for _ in range(10):
        recorder.submit(record())
    assert recorder.dropped >= 5
    store.gate.set()
    recorder.stop()
    assert recorder.written + recorder.dropped == 10


def test_a_store_that_fails_is_counted_and_the_worker_carries_on():
    store = ListStore()
    recorder = Recorder(store, batch_size=1, batch_ms=1)
    store.fail = True
    recorder.submit(record())
    recorder.drain()
    store.fail = False
    recorder.submit(record())
    assert recorder.drain()
    assert recorder.failed == 1 and recorder.written == 1
    recorder.stop()


def test_stop_writes_what_is_queued():
    store = ListStore()
    recorder = Recorder(store, batch_ms=1)
    for _ in range(20):
        recorder.submit(record())
    recorder.stop()
    assert recorder.written == 20
