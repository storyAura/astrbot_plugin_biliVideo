"""Build user-facing text/messages for video info & metadata."""

from __future__ import annotations

import contextlib
import time

from ..core.config import PluginConfig
from ..core.types import VideoInfo
from .chunker import format_count


def format_video_summary_lines(
    info: VideoInfo,
    *,
    config: PluginConfig,
    desc_max: int = 100,
) -> list[str]:
    """Build the text lines for an auto-detect "card-like" announcement.

    Each toggle in the config is honored; the caller decides whether to
    prepend a cover image component.
    """

    lines: list[str] = [f"📺 {info.title}"]
    if config.detect_show_uploader:
        lines.append(f"👤 UP主: {info.owner_name}")
    if config.detect_show_desc and info.desc:
        desc = info.desc
        if len(desc) > desc_max:
            desc = desc[:desc_max] + "..."
        lines.append(f"📝 简介: {desc}")
    if config.detect_show_pubtime and info.pubdate:
        try:
            pub_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(info.pubdate))
            lines.append(f"📅 发布: {pub_str}")
        except (ValueError, OSError):
            pass
    if config.detect_show_stats:
        lines.append(
            f"▶️ {format_count(info.view)}播放  "
            f"💬 {format_count(info.danmaku)}弹幕  "
            f"👍 {format_count(info.like)}点赞"
        )
    if config.detect_show_link:
        lines.append(f"🔗 {info.url}")
    return lines


def format_video_info_block(info: VideoInfo, *, desc_max: int = 150) -> str:
    """Compact info block used in forward-message nodes."""

    parts: list[str] = [f"👤 UP主: {info.owner_name}"]
    if info.desc:
        desc = info.desc
        if len(desc) > desc_max:
            desc = desc[:desc_max] + "..."
        parts.append(f"📝 简介: {desc}")
    if info.pubdate:
        with contextlib.suppress(ValueError, OSError):
            parts.append(
                f"📅 发布时间: {time.strftime('%Y-%m-%d %H:%M', time.localtime(info.pubdate))}"
            )
    parts.append(
        f"▶️ {format_count(info.view)}播放  "
        f"💬 {format_count(info.danmaku)}弹幕  "
        f"👍 {format_count(info.like)}点赞"
    )
    parts.append(f"🔗 {info.url}")
    return "\n".join(parts)
