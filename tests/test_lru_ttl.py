"""LRU+TTL cache tests."""

from __future__ import annotations

import asyncio

import pytest

from bilivideo.cache.lru_ttl import LRUTTLCache


@pytest.mark.asyncio
async def test_set_and_get() -> None:
    cache: LRUTTLCache[str, int] = LRUTTLCache(max_size=4, ttl_seconds=60)
    await cache.set("a", 1)
    assert await cache.get("a") == 1
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_eviction() -> None:
    cache: LRUTTLCache[str, int] = LRUTTLCache(max_size=2, ttl_seconds=60)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)  # evict a
    assert await cache.get("a") is None
    assert await cache.get("b") == 2
    assert await cache.get("c") == 3


@pytest.mark.asyncio
async def test_ttl_expiry() -> None:
    cache: LRUTTLCache[str, int] = LRUTTLCache(max_size=4, ttl_seconds=0.05)
    await cache.set("a", 1)
    assert await cache.get("a") == 1
    await asyncio.sleep(0.07)
    assert await cache.get("a") is None


@pytest.mark.asyncio
async def test_single_flight() -> None:
    cache: LRUTTLCache[str, int] = LRUTTLCache(max_size=4, ttl_seconds=60)
    counter = {"n": 0}

    async def factory() -> int:
        counter["n"] += 1
        await asyncio.sleep(0.05)
        return 42

    results = await asyncio.gather(*(cache.get_or_set("k", factory) for _ in range(5)))
    assert all(r == 42 for r in results)
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_get_or_set_caches_none_value() -> None:
    cache: LRUTTLCache[str, None] = LRUTTLCache(max_size=4, ttl_seconds=60)
    counter = {"n": 0}

    async def factory() -> None:
        counter["n"] += 1
        value: None = None
        return value

    assert await cache.get_or_set("k", factory) is None
    assert await cache.get_or_set("k", factory) is None
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_invalidate_and_clear() -> None:
    cache: LRUTTLCache[str, int] = LRUTTLCache(max_size=4, ttl_seconds=60)
    await cache.set("a", 1)
    await cache.invalidate("a")
    assert await cache.get("a") is None
    await cache.set("a", 2)
    await cache.clear()
    assert await cache.get("a") is None
