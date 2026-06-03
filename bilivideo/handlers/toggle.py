"""`/识别开关` handler."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..services import BiliVideoServices


async def handle_toggle_detect(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    services.enable_miniapp_detect = not services.enable_miniapp_detect
    services.runtime_state.set_bool("enable_miniapp_detect", services.enable_miniapp_detect)
    status = "✅ 已开启" if services.enable_miniapp_detect else "❌ 已关闭"
    yield event.plain_result(f"B站链接自动识别: {status}")  # type: ignore[attr-defined]
