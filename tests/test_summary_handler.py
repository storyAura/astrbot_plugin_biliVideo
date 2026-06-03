"""Manual summary URL extraction/canonicalization tests."""

from __future__ import annotations

import pytest

from bilivideo.handlers.summary import (
    _canonicalize_video_url,
    _extract_video_url,
    _is_platform_supported,
)


class _HTTP:
    def __init__(self, resolved: str | None) -> None:
        self.resolved = resolved
        self.urls: list[str] = []

    async def follow_redirect(self, url: str) -> str | None:
        self.urls.append(url)
        return self.resolved


class _Services:
    def __init__(self, resolved: str | None) -> None:
        self.http_client = _HTTP(resolved)


def test_manual_summary_cleans_short_url_argument() -> None:
    url = _extract_video_url("/总结 https://b23.tv/abc，", object())
    assert url == "https://b23.tv/abc"


def test_manual_summary_extracts_youtube_url() -> None:
    url = _extract_video_url("/总结 https://youtu.be/abc123，", object())
    assert url == "https://youtu.be/abc123"


def test_manual_summary_extracts_douyin_url() -> None:
    url = _extract_video_url("/总结 https://www.douyin.com/video/123)", object())
    assert url == "https://www.douyin.com/video/123"


def test_platform_support_respects_multi_platform_flag() -> None:
    assert _is_platform_supported(
        "https://www.bilibili.com/video/BV1xx411c7mD",
        enable_multi_platform=False,
    )
    assert not _is_platform_supported("https://youtu.be/abc", enable_multi_platform=False)
    assert _is_platform_supported("https://youtu.be/abc", enable_multi_platform=True)
    assert _is_platform_supported("https://www.douyin.com/video/123", enable_multi_platform=True)


@pytest.mark.asyncio
async def test_canonicalize_other_bili_short_domain() -> None:
    services = _Services("https://www.bilibili.com/video/BV1xx411c7mD")

    out = await _canonicalize_video_url(services, "https://bili2233.cn/abc")

    assert out == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert services.http_client.urls == ["https://bili2233.cn/abc"]


@pytest.mark.asyncio
async def test_canonicalize_short_url_failure_returns_empty() -> None:
    services = _Services(None)

    assert await _canonicalize_video_url(services, "https://b23.tv/bad") == ""


@pytest.mark.asyncio
async def test_canonicalize_keeps_non_bilibili_url_with_bv_like_text() -> None:
    services = _Services("https://www.bilibili.com/video/BV1xx411c7mD")
    url = "https://youtu.be/BV1xx411c7mD"

    assert await _canonicalize_video_url(services, url) == url
    assert services.http_client.urls == []
