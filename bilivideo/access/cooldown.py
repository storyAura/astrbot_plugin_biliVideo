"""Per-user cooldown (anti-spam) tracker."""

from __future__ import annotations

import time
from collections import OrderedDict


class CooldownTracker:
    """Sliding-window cooldown tracker with bounded memory.

    Stores the timestamp of the last successful trigger per key. Older
    entries are evicted lazily so a busy bot doesn't accumulate infinite
    state.
    """

    def __init__(self, *, window_seconds: int, max_entries: int = 4096) -> None:
        self._window = float(window_seconds)
        self._max = max_entries
        self._last: OrderedDict[str, float] = OrderedDict()

    @property
    def disabled(self) -> bool:
        return self._window <= 0

    def remaining(self, key: str) -> int:
        if self.disabled or not key:
            return 0
        ts = self._last.get(key)
        if ts is None:
            return 0
        delta = time.monotonic() - ts
        if delta >= self._window:
            return 0
        return max(0, int(self._window - delta) + 1)

    def punch(self, key: str) -> None:
        if self.disabled or not key:
            return
        self._last[key] = time.monotonic()
        self._last.move_to_end(key)
        while len(self._last) > self._max:
            self._last.popitem(last=False)

    def update_window(self, window_seconds: int) -> None:
        self._window = float(window_seconds)
