"""Push target helper tests."""

from __future__ import annotations

from bilivideo.core.config import PluginConfig
from bilivideo.handlers.push_target import _platform_prefix


class _Services:
    def __init__(self, prefix: str = "aiocqhttp") -> None:
        self.config = PluginConfig(platform_prefix=prefix)


def test_platform_prefix_prefers_event_origin() -> None:
    assert _platform_prefix(_Services("fallback"), "aiocqhttp:GroupMessage:1") == "aiocqhttp"


def test_platform_prefix_falls_back_to_config() -> None:
    assert _platform_prefix(_Services("napcat"), "") == "napcat"
