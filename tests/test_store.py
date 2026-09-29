from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from app.store import ResultStore, Snapshot

T0 = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)


def test_empty_store_has_no_result_and_is_stale():
    snap = ResultStore().snapshot()
    assert snap.result is None
    assert snap.is_stale(T0, 7200)


def test_set_result_replaces_snapshot():
    store = ResultStore()
    store.set_result({"v": 1}, T0)
    store.set_result({"v": 2}, T0 + timedelta(hours=1))

    snap = store.snapshot()
    assert snap.result == {"v": 2}
    assert snap.computed_at == T0 + timedelta(hours=1)
    assert snap.last_attempt_ok is True


def test_failure_keeps_last_good_result():
    store = ResultStore()
    store.set_result({"v": 1}, T0)
    store.record_failure(T0 + timedelta(hours=1))

    snap = store.snapshot()
    assert snap.result == {"v": 1}
    assert snap.computed_at == T0
    assert snap.last_attempt_at == T0 + timedelta(hours=1)
    assert snap.last_attempt_ok is False


def test_failure_before_any_result():
    store = ResultStore()
    store.record_failure(T0)
    snap = store.snapshot()
    assert snap.result is None
    assert snap.last_attempt_ok is False


def test_staleness_threshold():
    snap = Snapshot(result={}, computed_at=T0)
    assert not snap.is_stale(T0 + timedelta(seconds=7200), 7200)
    assert snap.is_stale(T0 + timedelta(seconds=7201), 7200)


def test_readers_never_see_a_torn_snapshot():
    # result and computed_at are written together: a reader must never pair
    # one write's result with another write's timestamp
    store = ResultStore()
    stop = threading.Event()
    torn: list[Snapshot] = []

    def writer():
        i = 0
        while not stop.is_set():
            store.set_result({"i": i}, T0 + timedelta(seconds=i))
            store.record_failure(T0 + timedelta(seconds=i))
            i += 1

    def reader():
        for _ in range(20_000):
            snap = store.snapshot()
            expected = T0 + timedelta(seconds=snap.result["i"]) if snap.result else None
            if snap.result is not None and snap.computed_at != expected:
                torn.append(snap)

    w = threading.Thread(target=writer)
    readers = [threading.Thread(target=reader) for _ in range(4)]
    w.start()
    for r in readers:
        r.start()
    for r in readers:
        r.join()
    stop.set()
    w.join()

    assert torn == []
