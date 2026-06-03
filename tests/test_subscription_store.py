"""Subscription manager / atomic store tests."""

from __future__ import annotations

import json

import pytest

from bilivideo.subscription.manager import SubscriptionManager


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
