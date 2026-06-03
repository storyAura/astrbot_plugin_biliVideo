"""CheckScheduler test using a stub callback."""

from __future__ import annotations

import asyncio

import pytest

from bilivideo.subscription.manager import Subscription, SubscriptionManager
from bilivideo.subscription.scheduler import CheckScheduler


@pytest.mark.asyncio
async def test_trigger_once_invokes_callback_for_each_sub(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o1", "u1", "n1")
    await mgr.add_subscription("o1", "u2", "n2")
    await mgr.add_subscription("o2", "u3", "n3")

    seen: list[tuple[str, str]] = []

    async def cb(origin: str, sub: Subscription) -> int:
        seen.append((origin, sub.mid))
        return 1 if sub.mid == "u2" else 0

    sched = CheckScheduler(
        mgr,
        cb,
        interval_seconds=999,
        startup_delay=0,
        per_request_pause=0,
    )
    triggered = await sched.trigger_once()
    assert triggered == 1
    assert {(o, m) for o, m in seen} == {("o1", "u1"), ("o1", "u2"), ("o2", "u3")}


@pytest.mark.asyncio
async def test_callback_error_does_not_stop_scheduler(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o", "u1", "n1")
    await mgr.add_subscription("o", "u2", "n2")

    invocations: list[str] = []

    async def cb(origin: str, sub: Subscription) -> int:
        invocations.append(sub.mid)
        if sub.mid == "u1":
            raise RuntimeError("boom")
        return 1

    sched = CheckScheduler(
        mgr,
        cb,
        interval_seconds=999,
        startup_delay=0,
        per_request_pause=0,
    )
    pushed = await sched.trigger_once()
    # Both UPs were attempted even though u1 raised
    assert invocations == ["u1", "u2"]
    assert pushed == 1


@pytest.mark.asyncio
async def test_stop_cleanly(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))

    async def cb(origin, sub):
        await asyncio.sleep(0.01)

    sched = CheckScheduler(
        mgr,
        cb,
        interval_seconds=999,
        startup_delay=0,
    )
    sched.start()
    await asyncio.sleep(0.05)
    await sched.stop()
    assert not sched.is_running()
