"""Cooldown tracker tests."""

from __future__ import annotations

import time

from bilivideo.access.cooldown import CooldownTracker


def test_disabled_when_zero() -> None:
    tracker = CooldownTracker(window_seconds=0)
    assert tracker.disabled
    tracker.punch("user")
    assert tracker.remaining("user") == 0


def test_active_window() -> None:
    tracker = CooldownTracker(window_seconds=2)
    tracker.punch("user")
    remaining = tracker.remaining("user")
    assert 0 < remaining <= 3


def test_eviction_after_window() -> None:
    tracker = CooldownTracker(window_seconds=1)
    tracker.punch("user")
    time.sleep(1.1)
    assert tracker.remaining("user") == 0


def test_unrelated_keys_isolated() -> None:
    tracker = CooldownTracker(window_seconds=10)
    tracker.punch("a")
    assert tracker.remaining("b") == 0
