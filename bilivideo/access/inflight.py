"""Deduplicates in-flight summary tasks.

If three users paste the same BV simultaneously we only do the work once;
the other two wait on the same Future and get the same answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Hashable
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class InflightDeduper(Generic[K, V]):
    """Tracks running coroutines keyed by `K`."""

    def __init__(self) -> None:
        self._pending: dict[K, asyncio.Future[V]] = {}
        self._lock = asyncio.Lock()

    async def run(self, key: K, factory: Callable[[], Awaitable[V]]) -> V:
        async with self._lock:
            existing = self._pending.get(key)
            if existing is not None:
                fut = existing
                owner = False
            else:
                fut = asyncio.get_running_loop().create_future()
                self._pending[key] = fut
                owner = True

        if not owner:
            return await fut

        try:
            value = await factory()
        except BaseException as exc:
            fut.set_exception(exc)
            async with self._lock:
                self._pending.pop(key, None)
            raise
        else:
            fut.set_result(value)
            async with self._lock:
                self._pending.pop(key, None)
            return value
