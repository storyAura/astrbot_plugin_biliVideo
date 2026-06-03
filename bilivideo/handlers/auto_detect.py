"""`on_all_message` auto-detect handler.

Refactored from a ~300-line nested branch in the original `main.py` into
clear stages:

  1. Reject obvious quoted/replied messages (the user is likely answering
     someone, not requesting a summary).
  2. Build a `MessageContext` so subsequent code knows what the user
     actually typed vs. what was quoted.
  3. Search a strict ordering of sources for a Bilibili URL.
  4. If found, fetch info via the typed API and send back the configured
     fields (cover, uploader, etc.). Optionally trigger a summary.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..access.control import is_allowed
from ..api.endpoints import get_video_info
from ..core.exceptions import BiliVideoError
from ..messaging.builders import format_video_summary_lines
from ..parsing.message_router import (
    looks_like_quoted_message,
    parse_event,
    url_from_card,
    url_from_raw_payload,
)
from ..parsing.triggers import TriggerSet
from ..parsing.url_extractor import (
    extract_bvid,
    extract_long_url,
    extract_short_url,
    is_bilibili_domain,
)
from ..services import BiliVideoServices
from ._render_helper import render_note_components
from ._send_helper import yield_note_response

try:
    from astrbot.api.message_components import Image, Plain  # type: ignore[import]
except Exception:  # pragma: no cover - test stub
    Image = Plain = None  # type: ignore[assignment]


async def handle_auto_detect(
    services: BiliVideoServices, event: object
) -> AsyncIterator[object]:
    if not services.enable_miniapp_detect:
        return

    ctx = parse_event(event)

    # Hard intercept: any message with reply markers is *not* a paste.
    if looks_like_quoted_message(ctx.raw_message, ctx.plain_text) or ctx.is_reply:
        triggers = TriggerSet(services.config.trigger_keywords)
        if not triggers.matches(ctx.plain_text):
            services.logger.debug("auto-detect skip: quoted message without trigger")
            return

    # Skip command messages
    if ctx.plain_text.strip().startswith("/"):
        return

    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        return

    # Skip pure @mention messages with no Bilibili hint
    if ctx.has_at and not TriggerSet.has_bilibili_hint(ctx.plain_text):
        return

    bvid = await _resolve_bvid(services, ctx, allow_full_text=not ctx.is_reply)
    if not bvid:
        return

    try:
        info = await get_video_info(services.http_client, bvid)
    except BiliVideoError as exc:
        services.logger.warning(f"video info fetch failed: {exc}")
        return

    chain: list[object] = []
    if services.config.detect_show_cover and info.normalized_pic and Image is not None:
        chain.append(Image.fromURL(info.normalized_pic))
    if Plain is not None:
        text = "\n".join(format_video_summary_lines(info, config=services.config))
        chain.append(Plain(text))

    if chain:
        yield event.chain_result(chain)  # type: ignore[attr-defined]

    if services.config.detect_auto_summary:
        yield event.plain_result("⏳ 正在生成视频总结...")  # type: ignore[attr-defined]
        try:
            note = await services.inflight.run(
                bvid, lambda: services.orchestrator.generate(info.url)
            )
        except BiliVideoError as exc:
            yield event.plain_result(exc.user_message)  # type: ignore[attr-defined]
            return
        components = render_note_components(services, note.markdown)
        async for resp in yield_note_response(services, event, components, video_info=info):
            yield resp


# ──────────────────────────── helpers ──────────────────────────────


async def _resolve_bvid(
    services: BiliVideoServices,
    ctx,
    *,
    allow_full_text: bool,
) -> str | None:
    """Run the resolution waterfall: card → JSON in raw → text → short URL."""

    # 1. JSON card from raw payload
    bili_url = url_from_raw_payload(ctx.raw_payload)

    # 2. JSON card stringified into a component
    if not bili_url and ctx.json_card_text:
        bili_url = url_from_card(ctx.json_card_text)

    # 3. message_str itself may be a JSON object (rare)
    if not bili_url and ctx.raw_message.strip().startswith("{"):
        bili_url = url_from_card(ctx.raw_message)

    # 4. text-based extraction
    text_pool = ctx.plain_text
    if allow_full_text and ctx.raw_message:
        text_pool = f"{text_pool} {ctx.raw_message}"

    if bili_url:
        bvid = extract_bvid(bili_url)
        if bvid:
            return bvid
        if is_bilibili_domain(bili_url):
            resolved = await services.http_client.follow_redirect(bili_url)
            if resolved:
                bvid = extract_bvid(resolved)
                if bvid:
                    return bvid

    bvid = extract_bvid(text_pool)
    if bvid:
        return bvid

    long_url = extract_long_url(text_pool)
    if long_url:
        bvid = extract_bvid(long_url)
        if bvid:
            return bvid

    short_url = extract_short_url(text_pool)
    if short_url:
        resolved = await services.http_client.follow_redirect(short_url)
        if resolved:
            return extract_bvid(resolved)

    return None
