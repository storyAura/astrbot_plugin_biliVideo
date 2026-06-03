"""`/总结模型` handler: list and switch the AstrBot built-in LLM model (issue #8).

Only meaningful in `astrbot` provider mode. AstrBot's static config schema
cannot render a dynamic dropdown of configured models, so this command lists
the available providers (by id + model) and lets the user pin one at runtime;
the choice is persisted in `runtime_state.json`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..access.control import is_allowed
from ..services import BiliVideoServices
from ._utils import parse_command_args

_RESET_TOKENS = {"默认", "默認", "default", "reset", "清除", "auto"}


async def handle_model(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    if services.config.is_openai_compatible:
        yield event.plain_result(  # type: ignore[attr-defined]
            "ℹ️ 当前为 openai_compatible 模式,/总结模型 仅在 astrbot 模式可用。\n"
            "如需切换内置模型,请将 llm_provider 设为 astrbot。"
        )
        return

    context = services.astrbot_context
    if context is None or not hasattr(context, "get_all_providers"):
        yield event.plain_result("❌ 无法访问 AstrBot 模型列表")  # type: ignore[attr-defined]
        return

    available = _list_providers(context)
    if not available:
        yield event.plain_result("❌ AstrBot 未配置任何对话模型(Provider)")  # type: ignore[attr-defined]
        return

    arg = parse_command_args(getattr(event, "message_str", "") or "")
    current = getattr(services.llm, "provider_id", "") or ""

    if not arg:
        yield event.plain_result(_format_list(available, current))  # type: ignore[attr-defined]
        return

    if arg in _RESET_TOKENS:
        _apply_provider_id(services, "")
        yield event.plain_result("✅ 已恢复为 AstrBot 当前默认模型")  # type: ignore[attr-defined]
        return

    if arg not in {pid for pid, _ in available}:
        yield event.plain_result(  # type: ignore[attr-defined]
            f"❌ 未找到模型 ID「{arg}」\n\n{_format_list(available, current)}"
        )
        return

    _apply_provider_id(services, arg)
    yield event.plain_result(f"✅ 已切换内置模型为: {arg}")  # type: ignore[attr-defined]


# ──────────────────────────── helpers ──────────────────────────────


def _list_providers(context: object) -> list[tuple[str, str]]:
    """Return ``[(provider_id, model_name), ...]`` for available chat providers."""

    out: list[tuple[str, str]] = []
    try:
        providers = context.get_all_providers()  # type: ignore[attr-defined]
    except Exception:
        return out
    for prov in providers or []:
        try:
            pid = str(prov.meta().id)
        except Exception:
            continue
        try:
            model = str(prov.get_model() or "")
        except Exception:
            model = ""
        out.append((pid, model))
    return out


def _format_list(available: list[tuple[str, str]], current: str) -> str:
    lines = ["📋 可用内置模型 (provider ID):", "━━━━━━━━━━━━━━━━━━━"]
    for pid, model in available:
        marker = "  ← 当前" if current and pid == current else ""
        suffix = f" (model: {model})" if model else ""
        lines.append(f"  • {pid}{suffix}{marker}")
    if not current:
        lines.append("\n当前使用: AstrBot 默认模型")
    lines.append("\n切换: /总结模型 <provider ID>")
    lines.append("恢复默认: /总结模型 默认")
    return "\n".join(lines)


def _apply_provider_id(services: BiliVideoServices, provider_id: str) -> None:
    if hasattr(services.llm, "provider_id"):
        services.llm.provider_id = provider_id  # type: ignore[attr-defined]
    services.runtime_state.set_str("llm_provider_id", provider_id)
