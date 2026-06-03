"""Access-control tests."""

from __future__ import annotations

from bilivideo.access.control import is_allowed
from bilivideo.core.config import PluginConfig


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
