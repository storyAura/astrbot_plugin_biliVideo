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
