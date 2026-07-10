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
            # shield: a cancelled waiter must not cancel the shared Future,
            # which would poison this key for every later caller (the owner's
            # set_result would raise InvalidStateError and skip the pop).
            return await asyncio.shield(fut)

        try:
            value = await factory()
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
                # mark retrieved so a waiter-less failure doesn't emit
                # "Future exception was never retrieved" at GC time
                fut.exception()
            raise
        else:
            if not fut.done():
                fut.set_result(value)
            return value
        finally:
            async with self._lock:
                self._pending.pop(key, None)
