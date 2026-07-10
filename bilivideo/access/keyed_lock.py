"""Per-key asyncio locks with automatic cleanup.

Serializes check-and-push for a single subscription so the scheduled push
loop and a concurrent manual `/检查更新` can't both push the same video.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager


class KeyedLocks:
    """One `asyncio.Lock` per key; an entry is dropped when its last user leaves."""

    def __init__(self) -> None:
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._refcounts: dict[Hashable, int] = {}

    def __len__(self) -> int:
        return len(self._locks)

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncIterator[None]:
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._refcounts[key] = self._refcounts.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            remaining = self._refcounts[key] - 1
            if remaining:
                self._refcounts[key] = remaining
            else:
                del self._refcounts[key]
                self._locks.pop(key, None)
