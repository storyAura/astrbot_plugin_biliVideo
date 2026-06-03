"""Async-aware LRU + TTL cache with single-flight semantics.

Designed for caching expensive `await`-able lookups (video info, WBI key,
short URL resolutions). Critical features:

  * **TTL** — entries expire automatically without sweeping a separate task.
  * **Bounded size** — keeps memory usage predictable (LRU eviction).
  * **Single-flight** — concurrent callers for the same key share one fetch
    so we don't hammer the upstream service when 5 users paste the same BV.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from typing import Final, Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

_MISSING: Final[object] = object()


class LRUTTLCache(Generic[K, V]):
    """An asyncio-safe cache combining LRU eviction and per-entry TTL."""

    __slots__ = ("_inflight", "_lock", "_max_size", "_store", "_ttl")

    def __init__(self, *, max_size: int, ttl_seconds: float) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._max_size = max_size
        self._ttl = float(ttl_seconds)
        self._store: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._inflight: dict[K, asyncio.Future[V]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    async def get(self, key: K) -> V | None:
        """Return a cached value or `None` if missing/expired."""

        async with self._lock:
            value = self._get_unlocked(key)
            return None if value is _MISSING else value

    async def set(self, key: K, value: V) -> None:
        async with self._lock:
            self._set_unlocked(key, value)

    async def invalidate(self, key: K) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    async def get_or_set(self, key: K, factory: Callable[[], Awaitable[V]]) -> V:
        """Get the cached value; if missing, run `factory()` exactly once.

        Concurrent callers asking for the same key wait on a shared Future.
        """

        async with self._lock:
            cached = self._get_unlocked(key)
            if cached is not _MISSING:
                return cached

            inflight = self._inflight.get(key)
            if inflight is None:
                inflight = asyncio.get_running_loop().create_future()
                self._inflight[key] = inflight
                owner = True
            else:
                owner = False

        if not owner:
            return await inflight

        try:
            value = await factory()
        except BaseException as exc:
            inflight.set_exception(exc)
            async with self._lock:
                self._inflight.pop(key, None)
            raise
        else:
            inflight.set_result(value)
            async with self._lock:
                self._inflight.pop(key, None)
                self._set_unlocked(key, value)
            return value

    # ------------------------------------------------------------------
    # internals (must hold _lock)
    # ------------------------------------------------------------------
    def _get_unlocked(self, key: K) -> V | object:
        entry = self._store.get(key)
        if entry is None:
            return _MISSING
        value, expires_at = entry
        if expires_at <= time.monotonic():
            del self._store[key]
            return _MISSING
        # mark as recently used
        self._store.move_to_end(key)
        return value

    def _set_unlocked(self, key: K, value: V) -> None:
        expires_at = time.monotonic() + self._ttl
        self._store[key] = (value, expires_at)
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    # introspection ------------------------------------------------------
    def __len__(self) -> int:
        return len(self._store)
