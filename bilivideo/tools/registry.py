"""AI function-call tools.

The previous version embedded these dataclasses at the top of `main.py`,
mixing the data model with command handling. This module isolates them so
the AstrBot integration is the only thing that changes when versions update.

The implementations gracefully no-op if the underlying AstrBot internals
(`FunctionTool`, `add_llm_tools`) are unavailable — keeping the plugin
loadable on minimal AstrBot installs.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from ..api.endpoints import search_videos
from ..core.logging import get_logger
from ..messaging.forward import build_video_forward_nodes
from ..services import BiliVideoServices

logger = get_logger("BiliVideo/Tools")

try:  # pragma: no cover - depends on installed AstrBot version
    from astrbot.api.event import MessageChain  # type: ignore[import]
    from astrbot.api.message_components import Image, Node, Nodes, Plain  # type: ignore[import]
    from astrbot.core.agent.tool import FunctionTool  # type: ignore[import]
except Exception:
    FunctionTool = None  # type: ignore[assignment]
    Image = Node = Nodes = Plain = MessageChain = None  # type: ignore[assignment]


def register_ai_tools(services: BiliVideoServices, astrbot_context: object) -> None:
    """Attach the search list/download tools to AstrBot's tool registry.

    Silently skips if `FunctionTool` is unavailable.
    """

    if FunctionTool is None or astrbot_context is None:
        logger.warning("AstrBot AI tools not available; skipping tool registration")
        return

    list_tool = _make_search_list_tool(services)
    download_tool = _make_search_download_tool(services, astrbot_context)
    add = getattr(astrbot_context, "add_llm_tools", None)
    if not callable(add):
        logger.warning("astrbot_context.add_llm_tools missing; tools not registered")
        return
    add(list_tool)
    add(download_tool)
    logger.info("registered AI tools: bilibili_search_list, bilibili_search_download")


# ──────────────────────────── tool: list ───────────────────────────


def _make_search_list_tool(services: BiliVideoServices) -> object:
    @dataclass
    class _SearchListTool(FunctionTool):  # type: ignore[misc]
        name: str = "bilibili_search_list"
        description: str = (
            "搜索B站视频并返回视频列表(包含BV号)。"
            "仅返回搜索结果,不下载转写视频内容。"
            "如需下载转写视频内容,请将选中的BV号传给 bilibili_search_download 工具。"
        )
        parameters: dict = field(
            default_factory=lambda: {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "count": {"type": "integer", "description": "返回视频数量"},
                    "order": {
                        "type": "string",
                        "description": "totalrank/click/pubdate/dm/stow",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "0=全部 1=10m内 2=10-30m 3=30-60m 4=60m+",
                    },
                },
                "required": ["keyword"],
            }
        )

        async def call(self, _ctx, **kwargs):  # type: ignore[override]
            keyword = (kwargs.get("keyword") or "").strip()
            if not keyword:
                return "错误:请提供搜索关键词"
            count = int(kwargs.get("count") or services.config.default_count)
            order = kwargs.get("order") or "totalrank"
            duration = int(kwargs.get("duration") or 0)
            if order not in ("totalrank", "click", "pubdate", "dm", "stow"):
                order = "totalrank"
            if duration not in (0, 1, 2, 3, 4):
                duration = 0
            try:
                result = await search_videos(
                    services.http_client,
                    keyword,
                    page_size=count,
                    order=order,
                    duration=duration,
                )
            except Exception as exc:
                logger.error(f"search list failed: {exc}", exc_info=True)
                return f"搜索失败: {exc}"
            if not result or not result.results:
                return f"未找到与「{keyword}」相关的视频"
            payload = {
                "keyword": keyword,
                "total": result.num_results,
                "returned": len(result.results),
                "videos": [
                    {
                        "index": i + 1,
                        "bvid": v.bvid,
                        "title": v.title,
                        "author": v.author,
                        "play": v.play,
                        "duration": v.duration,
                        "url": v.url,
                    }
                    for i, v in enumerate(result.results)
                ],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

    return _SearchListTool()


# ────────────────────────── tool: download ─────────────────────────


def _make_search_download_tool(
    services: BiliVideoServices, astrbot_context: object
) -> object:
    default_dl = services.config.default_download_count

    @dataclass
    class _SearchDownloadTool(FunctionTool):  # type: ignore[misc]
        name: str = "bilibili_search_download"
        description: str = (
            "下载并转写视频内容。先通过 bilibili_search_list 搜索获取BV号,再调用此工具下载转写。"
            f"bv_list 支持一次传入多个BV号,建议每次下载 {default_dl} 个左右。"
            "重要:调用一次即可,后台自动处理所有视频,完成后会自动唤醒你继续处理。"
        )
        parameters: dict = field(
            default_factory=lambda: {
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string", "description": "文件夹名称"},
                    "bv_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "BV号数组,如 ['BV1xxx','BV2yyy']",
                    },
                },
                "required": ["folder_name", "bv_list"],
            }
        )

        async def call(self, ctx, **kwargs):  # type: ignore[override]
            folder_name = (kwargs.get("folder_name") or "").strip()
            bv_list = kwargs.get("bv_list") or []
            if not folder_name:
                return "错误:请提供文件夹名称"
            if not isinstance(bv_list, list) or not bv_list:
                return "错误:请提供BV号列表"

            try:
                event = ctx.context.event
            except Exception as exc:
                return f"错误:获取会话上下文失败 - {exc}"

            new_task = asyncio.create_task(
                _process_bv_list(
                    services=services,
                    astrbot_context=astrbot_context,
                    event=event,
                    folder_name=folder_name,
                    bv_list=list(bv_list),
                )
            )
            services.replace_download_task(new_task)
            return f"已开始下载转写 {len(bv_list)} 个视频,完成后会自动通知你。"

    return _SearchDownloadTool()


async def _process_bv_list(
    *,
    services: BiliVideoServices,
    astrbot_context: object,
    event: object,
    folder_name: str,
    bv_list: list[str],
) -> None:
    show_progress = services.config.search_show_progress
    umo = getattr(event, "unified_msg_origin", "")

    async def progress_callback(progress: dict) -> None:
        if not show_progress and not progress.get("is_last"):
            return
        completed = progress.get("completed", 0)
        total = progress.get("total", 0)
        title = progress.get("title", "")
        success = progress.get("success", True)
        prefix = "✅" if success else "❌"
        line = f"{prefix} 进度: {completed}/{total} - {title}"
        if progress.get("is_last"):
            line += (
                f"\n📝 转写完成("
                f"成功{progress.get('success_count', 0)}个,失败{progress.get('failed_count', 0)}个),"
                f"即将为您分析..."
            )
        try:
            chain = MessageChain().message(line)
            await astrbot_context.send_message(umo, chain)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning(f"progress dispatch failed: {exc}")

    try:
        result = await services.search_service.process_bv_list(
            bv_list=bv_list,
            folder_name=folder_name,
            max_concurrent=services.config.search_max_concurrent,
            prefer_subtitle=services.config.prefer_subtitle,
            quality=services.config.download_quality,
            subtitle_langs=services.config.subtitle_langs,
            progress_callback=progress_callback,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error(f"search download task failed: {exc}", exc_info=True)
        await _safe_send_text(
            astrbot_context,
            umo,
            "❌ B站视频下载转写任务失败\n"
            f"📂 文件夹: {folder_name}\n"
            f"原因: {exc}",
        )
        return

    successful = [v for v in result.videos if v.success and v.transcript]
    if successful:
        try:
            await _send_combined_summary(
                services=services,
                astrbot_context=astrbot_context,
                event=event,
                successful=successful,
            )
            return
        except Exception as exc:
            logger.warning(f"combined summary path failed: {exc}", exc_info=True)

    completion = (
        "📝 B站视频下载转写任务已完成\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📂 文件夹: {folder_name}\n"
        f"✅ 成功: {result.success_count} 个\n"
        f"❌ 失败: {result.failed_count} 个\n"
        f"📁 文件位置: {result.folder_path}"
    )
    await _safe_send_text(astrbot_context, umo, completion)


async def _safe_send_text(astrbot_context: object, umo: str, text: str) -> None:
    if MessageChain is None:
        logger.warning(f"cannot send message, MessageChain unavailable: {text}")
        return
    try:
        await astrbot_context.send_message(umo, MessageChain().message(text))  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning(f"message dispatch failed: {exc}")


def build_combined_summary_prompt(successful: list) -> str:
    """Build the LLM summary prompt for one or more transcribed videos.

    `successful` items expose `.info` (may be None; when present has `.title`),
    `.bvid`, and `.transcript`. Each video is rendered as a 1-indexed
    `【视频 N】` block joined by blank lines, then embedded in the structured
    summary instructions.
    """

    transcript_text = "\n\n".join(
        f"【视频 {i + 1}】{v.info.title if v.info else v.bvid}\n{v.transcript}"
        for i, v in enumerate(successful)
    )
    return (
        "请为以下B站视频内容生成一份详细的结构化总结。\n\n"
        "要求:\n"
        "1. 使用 Markdown 格式\n"
        "2. 包含:核心观点、关键要点、时间线(如有)、总结\n"
        "3. 语言简洁清晰,突出重点\n"
        "4. 如果是多个视频,分别总结并加上视频标题\n\n"
        f"{transcript_text}"
    )


async def _send_combined_summary(
    *,
    services: BiliVideoServices,
    astrbot_context: object,
    event: object,
    successful: list,
) -> None:
    summary_prompt = build_combined_summary_prompt(successful)
    note_text = await services.llm.chat(summary_prompt, session_id="BiliVideo_search")

    from ..handlers._render_helper import render_note_components  # avoid circular import at top

    rendered = render_note_components(services, note_text)
    umo = getattr(event, "unified_msg_origin", "")

    if services.config.enable_forward_message and successful and successful[0].info is not None:
        try:
            if len(successful) > 1:
                # multi-video forward: build node list directly
                nodes = []
                bot_name = services.config.forward_bot_name
                bot_uin = services.config.forward_bot_uin
                nodes.append(
                    Node(
                        content=[Plain(f"📝 搜索结果总结(共 {len(successful)} 个视频)")],
                        name=bot_name,
                        uin=bot_uin,
                    )
                )
                for i, v in enumerate(successful, start=1):
                    info = v.info
                    parts = []
                    if info.normalized_pic:
                        parts.append(Image.fromURL(info.normalized_pic))
                    parts.append(
                        Plain(
                            f"📺 视频 {i}: {info.title}\n"
                            f"👤 UP主: {info.owner_name}\n"
                            f"🔗 {info.url}"
                        )
                    )
                    nodes.append(Node(content=parts, name=bot_name, uin=bot_uin))
                if isinstance(rendered, list):
                    for j, comp in enumerate(rendered):
                        label = "📝 AI 综合总结" if j == 0 else f"📝 AI 综合总结(第 {j + 1} 页)"
                        nodes.append(Node(content=[Plain(label), comp], name=bot_name, uin=bot_uin))
                else:
                    nodes.append(
                        Node(
                            content=[Plain(f"📝 AI 综合总结\n\n{rendered}")],
                            name=bot_name,
                            uin=bot_uin,
                        )
                    )
                forward = Nodes(nodes=nodes)
            else:
                forward = build_video_forward_nodes(
                    successful[0].info,
                    rendered,
                    bot_name=services.config.forward_bot_name,
                    bot_uin=services.config.forward_bot_uin,
                )
            chain = MessageChain()
            chain.chain.append(forward)  # type: ignore[attr-defined]
            await astrbot_context.send_message(umo, chain)  # type: ignore[attr-defined]
            return
        except Exception as exc:
            logger.warning(f"forward path failed: {exc}")

    # plain fallback
    if isinstance(rendered, list):
        for comp in rendered:
            chain = MessageChain()
            chain.chain.append(comp)  # type: ignore[attr-defined]
            await astrbot_context.send_message(umo, chain)  # type: ignore[attr-defined]
    else:
        await astrbot_context.send_message(umo, MessageChain().message(rendered))  # type: ignore[attr-defined]
