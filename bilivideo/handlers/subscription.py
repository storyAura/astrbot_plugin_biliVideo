"""Subscription-related command handlers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from ..access.control import is_allowed
from ..api.endpoints import (
    get_latest_videos,
    get_uploader_info,
    get_video_info,
    search_uploader_by_name,
)
from ..core.exceptions import BiliVideoError
from ..parsing.url_extractor import extract_uid
from ..services import BiliVideoServices
from ._render_helper import render_note_components
from ._send_helper import yield_note_response
from ._utils import parse_command_args


async def handle_subscribe(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    args = parse_command_args(getattr(event, "message_str", "") or "")
    if not args:
        yield event.plain_result(  # type: ignore[attr-defined]
            "❌ 请提供UP主UID、空间链接或昵称\n用法: /订阅 <UP主UID或昵称>"
        )
        return

    name = ""
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
        name = uploader.name
        yield event.plain_result(f"✅ 找到UP主【{name}】(UID:{mid})")  # type: ignore[attr-defined]

    origin = getattr(event, "unified_msg_origin", "")
    count = await services.subscription_manager.get_subscription_count(origin)
    if count >= services.config.max_subscriptions:
        yield event.plain_result(f"❌ 已达到最大订阅数 ({services.config.max_subscriptions})")  # type: ignore[attr-defined]
        return

    if not name:
        info = await get_uploader_info(services.http_client, mid)
        if info is not None:
            name = info.name
        else:
            videos = await get_latest_videos(services.http_client, mid, count=1)
            if videos:
                try:
                    video_info = await get_video_info(services.http_client, videos[0].bvid)
                    if video_info.owner_name:
                        name = video_info.owner_name
                except BiliVideoError as exc:
                    services.logger.debug(f"owner name lookup failed for {mid}: {exc}")
            if not name:
                name = f"UP主_{mid}"

    added = await services.subscription_manager.add_subscription(origin, mid, name)
    if added:
        videos = await get_latest_videos(services.http_client, mid, count=1)
        if videos:
            await services.subscription_manager.update_last_video(origin, mid, videos[0].bvid)
        yield event.plain_result(  # type: ignore[attr-defined]
            f"✅ 已订阅 UP主【{name}】(UID:{mid})\n有新视频时将自动推送总结"
        )
    else:
        yield event.plain_result(f"⚠️ 已经订阅了 UP主【{name}】(UID:{mid})")  # type: ignore[attr-defined]


async def handle_unsubscribe(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    args = parse_command_args(getattr(event, "message_str", "") or "")
    if not args:
        yield event.plain_result(  # type: ignore[attr-defined]
            "❌ 请提供UP主UID、空间链接或昵称\n用法: /取消订阅 <UP主UID或昵称>"
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

    origin = getattr(event, "unified_msg_origin", "")
    removed = await services.subscription_manager.remove_subscription(origin, mid)
    if removed:
        yield event.plain_result(f"✅ 已取消订阅 (UID:{mid})")  # type: ignore[attr-defined]
    else:
        yield event.plain_result(f"⚠️ 未找到该订阅 (UID:{mid})")  # type: ignore[attr-defined]


async def handle_list_subscriptions(
    services: BiliVideoServices, event: object
) -> AsyncIterator[object]:
    origin = getattr(event, "unified_msg_origin", "")
    if not is_allowed(origin, config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    subs = await services.subscription_manager.get_subscriptions(origin)
    if not subs:
        yield event.plain_result(  # type: ignore[attr-defined]
            "📋 当前没有订阅任何UP主\n使用 /订阅 <UID或昵称> 添加订阅"
        )
        return

    lines = ["📋 当前订阅列表:", "━━━━━━━━━━━━━━━━━━━"]
    for i, up in enumerate(subs, start=1):
        lines.append(f"  {i}. {up.name} (UID:{up.mid})")
    lines.append(f"\n共 {len(subs)} 个订阅")
    yield event.plain_result("\n".join(lines))  # type: ignore[attr-defined]


async def handle_check_updates(
    services: BiliVideoServices, event: object
) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    origin = getattr(event, "unified_msg_origin", "")
    subs = await services.subscription_manager.get_subscriptions(origin)
    if not subs:
        yield event.plain_result("📋 当前没有订阅任何UP主,无法检查更新")  # type: ignore[attr-defined]
        return

    yield event.plain_result(  # type: ignore[attr-defined]
        f"🔍 正在检查 {len(subs)} 个UP主的更新...\n这可能需要一些时间,请耐心等待"
    )

    found = 0
    for up in subs:
        try:
            videos = await get_latest_videos(services.http_client, up.mid, count=1)
            if not videos:
                continue
            latest = videos[0]
            if latest.bvid == up.last_bvid:
                continue
            if not up.last_bvid:
                await services.subscription_manager.update_last_video(origin, up.mid, latest.bvid)
                continue
            found += 1
            yield event.plain_result(  # type: ignore[attr-defined]
                f"🔔 UP主【{up.name}】有新视频!\n📺 {latest.title}\n⏳ 正在生成总结..."
            )
            try:
                note = await services.orchestrator.generate(
                    f"https://www.bilibili.com/video/{latest.bvid}"
                )
            except BiliVideoError as exc:
                services.logger.warning(
                    f"manual check summary failed for {up.name} bvid={latest.bvid}: {exc}"
                )
                await services.subscription_manager.update_last_video(origin, up.mid, latest.bvid)
                yield event.plain_result(  # type: ignore[attr-defined]
                    f"{exc.user_message}\n"
                    "⚠️ 已记录该视频,避免下次检查重复提醒。需要重试请手动发送 "
                    f"/总结 https://www.bilibili.com/video/{latest.bvid}"
                )
                continue
            components = render_note_components(services, note.markdown)
            async for resp in yield_note_response(services, event, components, video_info=note.video_info):
                yield resp
            await services.subscription_manager.update_last_video(origin, up.mid, latest.bvid)
            await asyncio.sleep(2)
        except BiliVideoError as exc:
            services.logger.warning(f"check failed for {up.name}: {exc}")

    if found == 0:
        yield event.plain_result("✅ 检查完成,所有订阅的UP主暂无新视频")  # type: ignore[attr-defined]
    else:
        yield event.plain_result(f"✅ 检查完成,共发现 {found} 个新视频")  # type: ignore[attr-defined]
