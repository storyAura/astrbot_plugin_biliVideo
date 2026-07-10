"""Scheduled push callback used by `CheckScheduler`.

Invoked once per UP per polling cycle. We:
  * fetch the latest video for the UP
  * compare against `last_bvid` to decide whether to push
  * either generate a summary + push it, or push the basic info if the
    user has disabled `auto_push_summary`
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from ..api.endpoints import get_latest_videos
from ..core.exceptions import BiliVideoError
from ..core.types import LatestVideo, VideoInfo
from ..messaging.forward import build_video_forward_nodes
from ..services import BiliVideoServices
from ..subscription.manager import Subscription
from ._render_helper import render_note_components

try:
    from astrbot.api.event import MessageChain  # type: ignore[import]
    from astrbot.api.message_components import Image, Plain  # type: ignore[import]
except Exception:  # pragma: no cover
    Plain = Image = MessageChain = None  # type: ignore[assignment]


async def push_callback(
    services: BiliVideoServices,
    origin: str,
    sub: Subscription,
) -> int:
    if services.astrbot_context is None:
        services.logger.error("push_callback: astrbot_context is None; cannot deliver push")
        return 0
    # Serialize per subscription and re-read state under the lock: `sub` is a
    # snapshot from scan start, so a concurrent manual /检查更新 may already
    # have pushed and recorded this video.
    async with services.push_locks.acquire((origin, sub.mid)):
        fresh = await services.subscription_manager.get_subscription(origin, sub.mid)
        if fresh is None:  # unsubscribed while waiting for the lock
            return 0
        return await _push_if_new(services, origin, fresh)


async def _push_if_new(
    services: BiliVideoServices,
    origin: str,
    sub: Subscription,
) -> int:
    try:
        videos = await get_latest_videos(services.http_client, sub.mid, count=1)
    except BiliVideoError as exc:
        services.logger.warning(f"latest fetch failed for {sub.name}: {exc}")
        return 0
    if not videos:
        return 0

    latest = videos[0]
    if latest.bvid == sub.last_bvid:
        return 0

    if not sub.last_bvid:
        await services.subscription_manager.update_last_video(origin, sub.mid, latest.bvid)
        return 0

    services.logger.info(f"new video for {sub.name}: {latest.title}")
    chain_components = await _build_chain(services, sub, latest)
    if not chain_components:
        services.logger.warning(f"empty push chain for {sub.name}; skipping send")
        return 0

    push_origins = await services.subscription_manager.get_push_origins() or [origin]
    sent_count = 0
    for target in push_origins:
        try:
            mc = MessageChain(chain=chain_components)
            await services.astrbot_context.send_message(target, mc)  # type: ignore[attr-defined]
            sent_count += 1
        except Exception as exc:
            services.logger.error(f"push to {target} failed: {exc}")

    if sent_count > 0:
        try:
            await services.subscription_manager.update_last_video(origin, sub.mid, latest.bvid)
        except OSError as exc:
            services.logger.error(
                f"pushed {latest.bvid} but persisting last_bvid failed: {exc}; may re-push next cycle"
            )
        return 1

    services.logger.warning(
        f"new video for {sub.name} was not marked as pushed because all targets failed: "
        f"bvid={latest.bvid} targets={push_origins}"
    )
    return 0


# ──────────────────────────── helpers ──────────────────────────────


async def _build_chain(
    services: BiliVideoServices,
    sub: Subscription,
    latest: LatestVideo,
) -> list[Any]:
    push_header = f"🔔 UP主【{sub.name}】发布了新视频!\n"
    config = services.config
    if Plain is None:  # AstrBot message components unavailable; cannot build a chain
        services.logger.error("scheduled push: Plain component unavailable; skipping")
        return []
    bvid = latest.bvid
    video_url = f"https://www.bilibili.com/video/{bvid}"
    info: VideoInfo | None = None

    if not config.auto_push_summary:
        # basic info only
        lines = [push_header + f"📺 {latest.title}"]
        if latest.description:
            desc = latest.description if len(latest.description) <= 100 else latest.description[:100] + "..."
            lines.append(f"📝 简介: {desc}")
        if latest.pubdate:
            with contextlib.suppress(ValueError, OSError):
                lines.append(
                    f"📅 发布: {time.strftime('%Y-%m-%d %H:%M', time.localtime(latest.pubdate))}"
                )
        lines.append(f"🔗 {video_url}")
        chain: list[Any] = []
        if latest.pic and Image is not None:
            chain.append(Image.fromURL(latest.pic))
        chain.append(Plain("\n".join(lines)))
        return chain

    # Generate summary
    try:
        note = await services.orchestrator.generate(video_url)
        info = note.video_info
        rendered = await render_note_components(services, note.markdown)
    except BiliVideoError as exc:
        services.logger.warning(f"summary generation failed: {exc}")
        rendered = exc.user_message

    if config.enable_forward_message and info is not None:
        try:
            forward = build_video_forward_nodes(
                info,
                rendered,
                bot_name=config.forward_bot_name,
                bot_uin=config.forward_bot_uin,
                header=push_header.rstrip(),
            )
            return [forward]
        except Exception as exc:
            services.logger.warning(f"forward path failed, fallback: {exc}")

    if isinstance(rendered, list):
        return [Plain(push_header), *list(rendered)]
    if info is not None:
        # fall back to header + info+rendered
        body = f"{push_header}━━━━━━━━━━━━━━━━━━━\n\n{rendered}"
        return [Plain(body)]
    return [Plain(push_header + str(rendered))]
