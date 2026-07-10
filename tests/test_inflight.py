"""InflightDeduper tests."""

from __future__ import annotations

import asyncio

import pytest

from bilivideo.access.inflight import InflightDeduper


@pytest.mark.asyncio
async def test_concurrent_callers_share_result() -> None:
    dedup: InflightDeduper[str, int] = InflightDeduper()
    counter = {"n": 0}

    async def factory() -> int:
        counter["n"] += 1
        await asyncio.sleep(0.05)
        return counter["n"]

    results = await asyncio.gather(*(dedup.run("k", factory) for _ in range(5)))
    assert all(r == 1 for r in results)


@pytest.mark.asyncio
async def test_exception_propagates() -> None:
    dedup: InflightDeduper[str, int] = InflightDeduper()

    async def boom() -> int:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        await dedup.run("k", boom)


@pytest.mark.asyncio
async def test_subsequent_calls_run_again_after_finish() -> None:
    dedup: InflightDeduper[str, int] = InflightDeduper()
    counter = {"n": 0}

    async def factory() -> int:
        counter["n"] += 1
        return counter["n"]

    a = await dedup.run("k", factory)
    b = await dedup.run("k", factory)
    assert a == 1
    assert b == 2


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_poison_key() -> None:
    """A waiter cancelled mid-await must not break the owner or later callers."""

    dedup: InflightDeduper[str, int] = InflightDeduper()
    started = asyncio.Event()

    async def slow_factory() -> int:
        started.set()
        await asyncio.sleep(0.05)
        return 42

    owner_task = asyncio.create_task(dedup.run("k", slow_factory))
    await started.wait()
    waiter_task = asyncio.create_task(dedup.run("k", slow_factory))
    await asyncio.sleep(0)  # let the waiter attach to the shared future

    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    # owner still completes normally
    assert await owner_task == 42

    # the key is not poisoned: a fresh call runs the factory again
    async def fresh() -> int:
        return 7

    assert await dedup.run("k", fresh) == 7
