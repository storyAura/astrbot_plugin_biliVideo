"""KeyedLocks: per-key serialization for the check-and-push paths."""

from __future__ import annotations

import asyncio

import pytest

from bilivideo.access.keyed_lock import KeyedLocks
from bilivideo.subscription.manager import SubscriptionManager


@pytest.mark.asyncio
async def test_same_key_serializes() -> None:
    locks = KeyedLocks()
    order: list[str] = []

    async def worker(tag: str) -> None:
        async with locks.acquire(("o", "mid")):
            order.append(f"{tag}:in")
            await asyncio.sleep(0.02)
            order.append(f"{tag}:out")

    await asyncio.gather(worker("a"), worker("b"))
    # No interleaving: the second worker enters only after the first left.
    assert order in (
        ["a:in", "a:out", "b:in", "b:out"],
        ["b:in", "b:out", "a:in", "a:out"],
    )


@pytest.mark.asyncio
async def test_different_keys_run_concurrently() -> None:
    locks = KeyedLocks()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with locks.acquire("k1"):
            entered.set()
            await release.wait()

    async def other() -> None:
        await entered.wait()
        async with locks.acquire("k2"):  # must not block on k1's holder
            release.set()

    await asyncio.wait_for(asyncio.gather(holder(), other()), timeout=2)


@pytest.mark.asyncio
async def test_locks_cleaned_up_after_use() -> None:
    locks = KeyedLocks()
    async with locks.acquire(("o", "1")):
        assert len(locks) == 1
    assert len(locks) == 0


@pytest.mark.asyncio
async def test_cleanup_waits_for_last_user() -> None:
    locks = KeyedLocks()

    async def worker() -> None:
        async with locks.acquire("k"):
            await asyncio.sleep(0.01)

    await asyncio.gather(worker(), worker(), worker())
    assert len(locks) == 0


@pytest.mark.asyncio
async def test_check_and_set_race_pushes_once(tmp_path) -> None:
    """Regression: manual /检查更新 and the scheduled loop share the lock and
    re-read `last_bvid` inside it, so one new video is pushed exactly once."""

    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o", "mid", "up")
    await mgr.update_last_video("o", "mid", "BV_old")

    locks = KeyedLocks()
    pushes: list[str] = []

    async def check_and_push() -> None:
        async with locks.acquire(("o", "mid")):
            fresh = await mgr.get_subscription("o", "mid")
            assert fresh is not None
            if fresh.last_bvid == "BV_new":
                return  # the other path already pushed this video
            await asyncio.sleep(0.01)  # simulate summary generation + send
            pushes.append("BV_new")
            await mgr.update_last_video("o", "mid", "BV_new")

    await asyncio.gather(check_and_push(), check_and_push())
    assert pushes == ["BV_new"]
