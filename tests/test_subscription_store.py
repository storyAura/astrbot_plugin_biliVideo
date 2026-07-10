"""Subscription manager / atomic store tests."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from bilivideo.subscription.manager import SubscriptionManager
from bilivideo.subscription.store import JsonStore, StoreClosedError


@pytest.mark.asyncio
async def test_add_and_remove(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    assert await mgr.add_subscription("origin1", "12345", "Foo")
    # idempotent
    assert not await mgr.add_subscription("origin1", "12345", "Foo")
    subs = await mgr.get_subscriptions("origin1")
    assert len(subs) == 1
    assert subs[0].mid == "12345"

    assert await mgr.remove_subscription("origin1", "12345")
    assert not await mgr.remove_subscription("origin1", "12345")
    assert await mgr.get_subscription_count("origin1") == 0


@pytest.mark.asyncio
async def test_update_last_video(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o", "u", "n")
    await mgr.update_last_video("o", "u", "BV1abc")
    subs = await mgr.get_subscriptions("o")
    assert subs[0].last_bvid == "BV1abc"


@pytest.mark.asyncio
async def test_atomic_write(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o", "u", "n")
    file_path = tmp_path / "subscriptions.json"
    assert file_path.exists()
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    assert "subscriptions" in payload
    assert "o" in payload["subscriptions"]


@pytest.mark.asyncio
async def test_push_targets(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    assert await mgr.add_push_target("origin-a", "群1")
    assert not await mgr.add_push_target("origin-a", "群1")
    targets = await mgr.get_push_targets()
    assert len(targets) == 1
    assert targets[0].label == "群1"

    assert await mgr.remove_push_target("群1")
    assert not await mgr.remove_push_target("群1")


@pytest.mark.asyncio
async def test_all_subscriptions(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o1", "u1", "n1")
    await mgr.add_subscription("o2", "u2", "n2")
    all_subs = await mgr.all_subscriptions()
    assert set(all_subs.keys()) == {"o1", "o2"}


@pytest.mark.asyncio
async def test_get_subscription_single(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o", "u1", "n1")
    sub = await mgr.get_subscription("o", "u1")
    assert sub is not None
    assert sub.name == "n1"
    assert await mgr.get_subscription("o", "missing") is None
    assert await mgr.get_subscription("other", "u1") is None


@pytest.mark.asyncio
async def test_persist_failure_raises_and_rolls_back(tmp_path, monkeypatch) -> None:
    """Disk failure must propagate to the caller and leave memory matching
    the last successfully persisted state (no silent divergence)."""

    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o", "u1", "n1")

    def _boom(self: Path, target: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", _boom)
    with pytest.raises(OSError):
        await mgr.add_subscription("o", "u2", "n2")
    monkeypatch.undo()

    subs = await mgr.get_subscriptions("o")
    assert [s.mid for s in subs] == ["u1"]
    payload = json.loads((tmp_path / "subscriptions.json").read_text(encoding="utf-8"))
    assert [u["mid"] for u in payload["subscriptions"]["o"]["up_list"]] == ["u1"]


@pytest.mark.asyncio
async def test_mutator_failure_rolls_back(tmp_path) -> None:
    store = JsonStore(tmp_path / "s.json", default={"items": []})

    def bad(data: dict) -> None:
        data["items"].append("x")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await store.mutate(bad)
    assert (await store.read())["items"] == []


@pytest.mark.asyncio
async def test_cancelled_mutate_keeps_mutation(tmp_path) -> None:
    """Cancellation can't interrupt the worker thread, so the mutation is
    kept in memory: once the orphaned write lands, memory and disk agree."""

    store = JsonStore(tmp_path / "s.json", default={"v": 0})
    gate = threading.Event()
    original_write = store._write_atomic

    def slow_write(payload: str, seq: int) -> None:
        gate.wait(5)
        original_write(payload, seq)

    store._write_atomic = slow_write  # type: ignore[method-assign]
    task = asyncio.create_task(store.mutate(lambda d: d.__setitem__("v", 1)))
    await asyncio.sleep(0.05)  # let mutate reach the in-thread write
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    gate.set()

    assert (await store.read())["v"] == 1  # memory kept the mutation
    for _ in range(100):  # wait for the orphaned thread to finish the write
        target = tmp_path / "s.json"
        if target.exists() and json.loads(target.read_text(encoding="utf-8")) == {"v": 1}:
            break
        await asyncio.sleep(0.02)
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8")) == {"v": 1}


@pytest.mark.asyncio
async def test_stale_write_cannot_clobber_newer(tmp_path) -> None:
    """The sequence guard drops a late (orphaned) write that lost the race."""

    store = JsonStore(tmp_path / "s.json", default={"v": 0})
    store._write_atomic('{"v": 2}', 2)  # newer write lands first
    store._write_atomic('{"v": 1}', 1)  # stale orphan must be discarded
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8")) == {"v": 2}


@pytest.mark.asyncio
async def test_closed_store_refuses_mutations(tmp_path) -> None:
    mgr = SubscriptionManager(str(tmp_path))
    await mgr.add_subscription("o", "u1", "n1")
    mgr.close()
    with pytest.raises(StoreClosedError):
        await mgr.add_subscription("o", "u2", "n2")
    # reads still work
    assert [s.mid for s in await mgr.get_subscriptions("o")] == ["u1"]
