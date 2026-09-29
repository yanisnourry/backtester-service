"""Latest backtest result, held in memory and swapped atomically."""
from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Snapshot:
    result: dict[str, Any] | None = None
    computed_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_attempt_ok: bool | None = None

    def is_stale(self, now: datetime, max_age_seconds: float) -> bool:
        """True when there is no result, or the last good one is too old."""
        if self.computed_at is None:
            return True
        return (now - self.computed_at).total_seconds() > max_age_seconds


class ResultStore:
    """Readers get an immutable snapshot; a failed refresh never drops the last result."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = Snapshot()

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot

    def set_result(self, result: dict[str, Any], at: datetime) -> None:
        with self._lock:
            self._snapshot = Snapshot(
                result=result, computed_at=at, last_attempt_at=at, last_attempt_ok=True
            )

    def record_failure(self, at: datetime) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot, last_attempt_at=at, last_attempt_ok=False
            )
