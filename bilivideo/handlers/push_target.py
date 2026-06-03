"""Push-target command handlers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..access.control import is_allowed
from ..services import BiliVideoServices
from ._utils import parse_command_args


def _platform_prefix(services: BiliVideoServices, origin: str) -> str:
    prefix = origin.split(":", 1)[0].strip() if ":" in origin else ""
    return prefix or services.config.platform_prefix


async def handle_add_push_group(
    services: BiliVideoServices, event: object
) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    args = parse_command_args(getattr(event, "message_str", "") or "")
    if not args or not args.isdigit():
        yield event.plain_result("❌ 请提供QQ群号\n用法: /添加推送群 <群号>")  # type: ignore[attr-defined]
        return

    origin = getattr(event, "unified_msg_origin", "")
    prefix = _platform_prefix(services, origin)
    if not prefix:
        yield event.plain_result("❌ 无法识别当前平台,请先配置 platform_prefix")  # type: ignore[attr-defined]
        return
    target_origin = f"{prefix}:GroupMessage:{args}"
    added = await services.subscription_manager.add_push_target(target_origin, f"群{args}")
    msg = f"✅ 已添加推送目标: 群 {args}" if added else f"⚠️ 群 {args} 已在推送列表中"
    yield event.plain_result(msg)  # type: ignore[attr-defined]


async def handle_add_push_user(
    services: BiliVideoServices, event: object
) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    args = parse_command_args(getattr(event, "message_str", "") or "")
    if not args or not args.isdigit():
        yield event.plain_result("❌ 请提供QQ号\n用法: /添加推送号 <QQ号>")  # type: ignore[attr-defined]
        return

    origin = getattr(event, "unified_msg_origin", "")
    prefix = _platform_prefix(services, origin)
    if not prefix:
        yield event.plain_result("❌ 无法识别当前平台,请先配置 platform_prefix")  # type: ignore[attr-defined]
        return
    target_origin = f"{prefix}:FriendMessage:{args}"
    added = await services.subscription_manager.add_push_target(target_origin, f"QQ{args}")
    msg = f"✅ 已添加推送目标: QQ {args}" if added else f"⚠️ QQ {args} 已在推送列表中"
    yield event.plain_result(msg)  # type: ignore[attr-defined]


async def handle_list_push(
    services: BiliVideoServices, event: object
) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    targets = await services.subscription_manager.get_push_targets()
    if not targets:
        yield event.plain_result(  # type: ignore[attr-defined]
            "📋 当前没有配置推送目标\n"
            "使用 /添加推送群 <群号> 或 /添加推送号 <QQ号> 添加\n"
            "⚠️ 未配置推送目标时,总结将推送到发起订阅的群"
        )
        return

    lines = ["📋 当前推送目标:", "━━━━━━━━━━━━━━━━━━━"]
    for i, t in enumerate(targets, start=1):
        lines.append(f"  {i}. {t.label}")
    lines.append(f"\n共 {len(targets)} 个推送目标")
    yield event.plain_result("\n".join(lines))  # type: ignore[attr-defined]


async def handle_remove_push(
    services: BiliVideoServices, event: object
) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    args = parse_command_args(getattr(event, "message_str", "") or "")
    if not args:
        yield event.plain_result("❌ 请提供要移除的群号或QQ号\n用法: /移除推送 <群号或QQ号>")  # type: ignore[attr-defined]
        return

    removed = (
        await services.subscription_manager.remove_push_target(f"群{args}")
        or await services.subscription_manager.remove_push_target(f"QQ{args}")
        or await services.subscription_manager.remove_push_target(args)
    )
    msg = f"✅ 已移除推送目标: {args}" if removed else f"⚠️ 未找到该推送目标: {args}"
    yield event.plain_result(msg)  # type: ignore[attr-defined]
