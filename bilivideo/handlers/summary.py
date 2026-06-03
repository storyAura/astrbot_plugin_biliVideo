"""`/总结` and `/最新视频` handlers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..access.control import is_allowed
from ..api.endpoints import get_latest_videos, search_uploader_by_name
from ..core.exceptions import BiliVideoError
from ..core.logging import get_logger
from ..parsing.url_extractor import (
    detect_platform,
    extract_bvid,
    extract_long_url,
    extract_short_url,
    extract_uid,
    extract_url,
    is_short_bili_url,
)
from ..services import BiliVideoServices
from ._render_helper import render_note_components
from ._send_helper import yield_note_response
from ._utils import parse_command_args

logger = get_logger("BiliVideo/SummaryHandler")


async def handle_summary(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    origin = getattr(event, "unified_msg_origin", "")
    if not is_allowed(origin, config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    cooldown_key = f"sum:{getattr(event, 'get_sender_id', lambda: '')()}"
    remaining = services.cooldown.remaining(cooldown_key)
    if remaining > 0:
        yield event.plain_result(f"⏳ 操作太频繁,请等 {remaining} 秒后再试")  # type: ignore[attr-defined]
        return

    raw_msg = getattr(event, "message_str", "") or ""
    video_url = _extract_video_url(raw_msg, event)
    if not video_url:
        yield event.plain_result(  # type: ignore[attr-defined]
            "❌ 请提供视频链接\n用法: /总结 <B站视频链接>\n"
            "示例: /总结 https://www.bilibili.com/video/BV1xx..."
        )
        return

    if not _is_platform_supported(video_url, enable_multi_platform=services.config.enable_multi_platform):
        if services.config.enable_multi_platform:
            yield event.plain_result("❌ 仅支持 B站 / YouTube / 抖音 视频链接")  # type: ignore[attr-defined]
        else:
            yield event.plain_result("❌ 目前仅支持B站视频链接")  # type: ignore[attr-defined]
        return

    video_url = await _canonicalize_video_url(services, video_url)
    if not video_url:
        yield event.plain_result("❌ 短链解析失败,请检查链接是否有效或直接发送 BV 号")  # type: ignore[attr-defined]
        return

    yield event.plain_result("⏳ 正在生成总结,请稍候(可能需要 1-3 分钟)...")  # type: ignore[attr-defined]
    services.cooldown.punch(cooldown_key)

    dedup_key = extract_bvid(video_url) or video_url
    try:
        note = await services.inflight.run(
            dedup_key, lambda: services.orchestrator.generate(video_url)
        )
    except BiliVideoError as exc:
        yield event.plain_result(exc.user_message)  # type: ignore[attr-defined]
        return

    components = render_note_components(services, note.markdown)
    async for resp in yield_note_response(services, event, components, video_info=note.video_info):
        yield resp


async def handle_latest_video(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    args = parse_command_args(getattr(event, "message_str", "") or "")
    if not args:
        yield event.plain_result(  # type: ignore[attr-defined]
            "❌ 请提供UP主UID、空间链接或昵称\n用法: /最新视频 <UP主UID或昵称>"
        )
        return

    mid = extract_uid(args)
    if not mid:
        yield event.plain_result(f"🔍 正在搜索UP主: {args}...")  # type: ignore[attr-defined]
        uploader = await search_uploader_by_name(services.http_client, args)
        if uploader is None:
            yield event.plain_result(  # type: ignore[attr-defined]
                "❌ 无法识别UP主\n支持: 纯数字UID、空间链接、或UP主昵称"
            )
            return
        mid = uploader.mid
        yield event.plain_result(f"✅ 找到UP主【{uploader.name}】(UID:{mid})")  # type: ignore[attr-defined]

    yield event.plain_result(f"⏳ 正在获取UP主 (UID:{mid}) 的最新视频...")  # type: ignore[attr-defined]

    videos = await get_latest_videos(services.http_client, mid, count=1)
    if not videos:
        yield event.plain_result("❌ 未找到该UP主的视频")  # type: ignore[attr-defined]
        return

    video = videos[0]
    yield event.plain_result(  # type: ignore[attr-defined]
        f"📺 找到最新视频: {video.title}\n⏳ 正在生成总结..."
    )

    try:
        note = await services.inflight.run(
            video.bvid,
            lambda: services.orchestrator.generate(
                f"https://www.bilibili.com/video/{video.bvid}"
            ),
        )
    except BiliVideoError as exc:
        yield event.plain_result(exc.user_message)  # type: ignore[attr-defined]
        return

    components = render_note_components(services, note.markdown)
    async for resp in yield_note_response(services, event, components, video_info=note.video_info):
        yield resp


# ──────────────────────────── helpers ──────────────────────────────


def _is_platform_supported(video_url: str, *, enable_multi_platform: bool) -> bool:
    platform = detect_platform(video_url)
    if platform == "bilibili":
        return True
    return bool(enable_multi_platform and platform in ("youtube", "douyin"))


def _extract_video_url(raw_msg: str, event: object) -> str:
    full_text = raw_msg
    message_obj = getattr(event, "message_obj", None)
    if message_obj is not None:
        chain = getattr(message_obj, "message", None) or []
        plain_pieces: list[str] = []
        for comp in chain:
            text = getattr(comp, "text", None)
            if isinstance(text, str):
                plain_pieces.append(text)
            elif isinstance(comp, str):
                plain_pieces.append(comp)
        if plain_pieces:
            full_text = " ".join(plain_pieces)

    args = parse_command_args(raw_msg)
    if args:
        first = args.split()[0]
        bvid = extract_bvid(first)
        if bvid:
            return f"https://www.bilibili.com/video/{bvid}"
        long_url = extract_long_url(first)
        if long_url:
            return long_url
        short_url = extract_short_url(first)
        if short_url:
            return short_url
        generic_url = extract_url(first)
        if generic_url:
            return generic_url

    long_url = extract_long_url(raw_msg) or extract_long_url(full_text)
    if long_url:
        return long_url.rstrip(">")

    short_url = extract_short_url(raw_msg) or extract_short_url(full_text)
    if short_url:
        return short_url

    generic_url = extract_url(raw_msg) or extract_url(full_text)
    if generic_url:
        return generic_url

    bvid = extract_bvid(raw_msg) or extract_bvid(full_text)
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    return ""


async def _canonicalize_video_url(services: BiliVideoServices, video_url: str) -> str:
    if detect_platform(video_url) != "bilibili":
        return video_url
    bvid = extract_bvid(video_url)
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    if not is_short_bili_url(video_url):
        return video_url
    logger.debug(f"resolving manual summary short url={video_url}")
    resolved = await services.http_client.follow_redirect(video_url)
    if not resolved:
        logger.warning(f"short url resolve failed: {video_url}")
        return ""
    bvid = extract_bvid(resolved)
    if not bvid:
        logger.warning(f"short url resolved without bvid: {resolved}")
        return ""
    logger.debug(f"resolved b23 short url to bvid={bvid}")
    return f"https://www.bilibili.com/video/{bvid}"
