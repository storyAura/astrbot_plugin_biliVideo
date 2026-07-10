"""Access-control tests."""

from __future__ import annotations

import pytest

from bilivideo.access.control import is_allowed
from bilivideo.core.config import PluginConfig
from bilivideo.handlers._utils import ACCESS_DENIED_MESSAGE, require_access


def _cfg(mode: str, group_list: tuple[str, ...] = ()) -> PluginConfig:
    return PluginConfig(access_mode=mode, group_list=group_list)


def test_no_list_allowed() -> None:
    assert is_allowed("aiocqhttp:GroupMessage:111", config=_cfg("blacklist"))


def test_blacklist_blocks() -> None:
    cfg = _cfg("blacklist", ("123",))
    assert is_allowed("aiocqhttp:GroupMessage:456", config=cfg)
    assert not is_allowed("aiocqhttp:GroupMessage:123", config=cfg)


def test_whitelist_lets_listed_in() -> None:
    cfg = _cfg("whitelist", ("123",))
    assert is_allowed("aiocqhttp:GroupMessage:123", config=cfg)
    assert not is_allowed("aiocqhttp:GroupMessage:999", config=cfg)


def test_empty_origin_allowed() -> None:
    cfg = _cfg("whitelist", ("123",))
    assert is_allowed("", config=cfg)


def test_whitelist_rejects_suffix_collision() -> None:
    """Group id must match a whole origin segment, not a mere suffix."""

    cfg = _cfg("whitelist", ("10000",))
    assert is_allowed("aiocqhttp:GroupMessage:10000", config=cfg)
    assert not is_allowed("aiocqhttp:GroupMessage:910000", config=cfg)
    assert not is_allowed("aiocqhttp:GroupMessage:100001", config=cfg)


def test_blacklist_does_not_block_suffix_collision() -> None:
    cfg = _cfg("blacklist", ("10000",))
    assert not is_allowed("aiocqhttp:GroupMessage:10000", config=cfg)
    assert is_allowed("aiocqhttp:GroupMessage:910000", config=cfg)


# ────────────────────── require_access decorator ──────────────────────


class _FakeEvent:
    def __init__(self, origin: str) -> None:
        self.unified_msg_origin = origin

    def plain_result(self, text: str) -> str:
        return f"plain:{text}"


class _FakeServices:
    def __init__(self, config: PluginConfig) -> None:
        self.config = config


@require_access
async def _guarded(services: _FakeServices, event: _FakeEvent):
    yield event.plain_result("ok")


@pytest.mark.asyncio
async def test_require_access_denies_blocked_origin() -> None:
    services = _FakeServices(_cfg("whitelist", ("123",)))
    event = _FakeEvent("aiocqhttp:GroupMessage:999")
    results = [item async for item in _guarded(services, event)]
    assert results == [f"plain:{ACCESS_DENIED_MESSAGE}"]


@pytest.mark.asyncio
async def test_require_access_passes_allowed_origin() -> None:
    services = _FakeServices(_cfg("whitelist", ("123",)))
    event = _FakeEvent("aiocqhttp:GroupMessage:123")
    results = [item async for item in _guarded(services, event)]
    assert results == ["plain:ok"]


def test_require_access_preserves_handler_name() -> None:
    assert _guarded.__name__ == "_guarded"
