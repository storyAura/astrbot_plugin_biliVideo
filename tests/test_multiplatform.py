"""Multi-platform support gate tests."""

from __future__ import annotations

from bilivideo.core.config import PluginConfig
from bilivideo.handlers.summary import _is_platform_supported


def test_bilibili_always_supported() -> None:
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    assert _is_platform_supported(url, enable_multi_platform=False) is True
    assert _is_platform_supported(url, enable_multi_platform=True) is True


def test_youtube_supported_only_with_flag() -> None:
    short = "https://youtu.be/xxx"
    full = "https://www.youtube.com/watch?v=xxx"
    assert _is_platform_supported(short, enable_multi_platform=False) is False
    assert _is_platform_supported(full, enable_multi_platform=False) is False
    assert _is_platform_supported(short, enable_multi_platform=True) is True
    assert _is_platform_supported(full, enable_multi_platform=True) is True


def test_douyin_supported_only_with_flag() -> None:
    url = "https://www.douyin.com/video/123"
    assert _is_platform_supported(url, enable_multi_platform=False) is False
    assert _is_platform_supported(url, enable_multi_platform=True) is True


def test_non_video_url_never_supported() -> None:
    url = "https://example.com"
    assert _is_platform_supported(url, enable_multi_platform=False) is False
    assert _is_platform_supported(url, enable_multi_platform=True) is False


def test_enable_multi_platform_config() -> None:
    assert PluginConfig.from_mapping({"enable_multi_platform": True}).enable_multi_platform is True
    assert PluginConfig.from_mapping({}).enable_multi_platform is False
