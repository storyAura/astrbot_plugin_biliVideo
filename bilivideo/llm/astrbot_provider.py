"""LLM provider that delegates to AstrBot's configured Provider."""

from __future__ import annotations

import contextlib

from ..core.exceptions import LLMError
from ..core.logging import get_logger
from .structured_summary import (
    SUMMARY_TOOL_NAME,
    StructuredSummaryAttempt,
    summary_tool_parameters,
)

logger = get_logger("BiliVideo/LLM/AstrBot")

try:  # pragma: no cover - available inside AstrBot, absent in isolated tests
    from astrbot.core.agent.tool import FunctionTool, ToolSet
except Exception:  # pragma: no cover
    FunctionTool = None  # type: ignore[assignment,misc]
    ToolSet = None  # type: ignore[assignment,misc]


class AstrbotProvider:
    """Calls `context.get_using_provider().text_chat()`.

    The AstrBot framework hands us a `Context` object; we keep a weak
    handle so the provider object stays in sync with whatever the user
    selected in the AstrBot dashboard.
    """

    def __init__(self, astrbot_context: object | None, provider_id: str = "") -> None:
        self._context = astrbot_context
        self.provider_id = provider_id
        self._tool_capabilities: dict[tuple[str, str], bool] = {}

    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
        provider = self._resolve_provider()
        try:
            response = await provider.text_chat(
                prompt=prompt,
                session_id=session_id or "BiliVideo_plugin",
            )
        except Exception as exc:  # pragma: no cover - relies on AstrBot
            raise LLMError(f"AstrBot text_chat failed: {exc}") from exc
        return self._response_text(response)

    def cache_identity(self) -> str:
        """Return the current AstrBot provider/model identity for summary caching."""

        provider_name, model = self._capability_key(self._resolve_provider())
        return f"{provider_name}:{model}"

    async def chat_structured_summary(
        self,
        prompt: str,
        *,
        include_ai_summary: bool,
        style: str,
        session_id: str | None = None,
    ) -> StructuredSummaryAttempt:
        """Ask an AstrBot model for one required schema-only tool call."""

        provider = self._resolve_provider()
        capability_key = self._capability_key(provider)
        if self._tool_capabilities.get(capability_key) is False:
            return StructuredSummaryAttempt()

        provider_config = getattr(provider, "provider_config", None)
        modalities = provider_config.get("modalities") if isinstance(provider_config, dict) else None
        if isinstance(modalities, list) and modalities and "tool_use" not in modalities:
            self._tool_capabilities[capability_key] = False
            return StructuredSummaryAttempt()

        if FunctionTool is None or ToolSet is None:
            logger.info("AstrBot function tools unavailable; using Markdown output")
            self._tool_capabilities[capability_key] = False
            return StructuredSummaryAttempt()

        tool = FunctionTool(
            name=SUMMARY_TOOL_NAME,
            description=(
                "提交结构化视频总结。这是唯一允许的输出方式，"
                "每个章节都必须带对应的整数秒时间戳。"
            ),
            parameters=summary_tool_parameters(
                include_ai_summary=include_ai_summary,
                style=style,
            ),
            handler=None,
        )
        try:
            response = await provider.text_chat(
                prompt=prompt,
                session_id=session_id or "BiliVideo_plugin",
                func_tool=ToolSet([tool]),
                tool_choice="required",
            )
        except Exception as exc:  # pragma: no cover - provider-specific errors
            if self._is_tool_unsupported(exc):
                logger.info(f"AstrBot model does not support tools; using Markdown output: {exc}")
                self._tool_capabilities[capability_key] = False
                return StructuredSummaryAttempt()
            raise LLMError(f"AstrBot structured summary failed: {exc}") from exc

        names = getattr(response, "tools_call_name", None) or []
        arguments = getattr(response, "tools_call_args", None) or []
        for name, payload in zip(names, arguments, strict=False):
            if name == SUMMARY_TOOL_NAME:
                self._tool_capabilities[capability_key] = True
                return StructuredSummaryAttempt(arguments=payload)

        # Some AstrBot providers remove unsupported tools internally and retry
        # the same dual-mode prompt as text. Reuse that response when present.
        return StructuredSummaryAttempt(fallback_text=self._response_text(response))

    def _resolve_provider(self):
        if self._context is None or not hasattr(self._context, "get_using_provider"):
            raise LLMError("AstrBot context unavailable")
        if self.provider_id:
            provider = self._context.get_provider_by_id(self.provider_id)
            if provider is None:
                logger.warning(
                    f"provider id '{self.provider_id}' not found; using AstrBot current provider"
                )
                provider = self._context.get_using_provider()
        else:
            provider = self._context.get_using_provider()
        if provider is None:
            raise LLMError("AstrBot has no LLM provider configured")
        return provider

    @staticmethod
    def _response_text(response: object) -> str:
        if hasattr(response, "completion_text"):
            return str(response.completion_text or "").strip()
        if isinstance(response, str):
            return response.strip()
        return str(response).strip()

    @staticmethod
    def _capability_key(provider: object) -> tuple[str, str]:
        provider_name = type(provider).__name__
        with contextlib.suppress(Exception):
            provider_name = str(provider.meta().id)  # type: ignore[attr-defined]
        try:
            model = str(provider.get_model() or "")  # type: ignore[attr-defined]
        except Exception:
            model = ""
        return provider_name, model

    @staticmethod
    def _is_tool_unsupported(exc: Exception) -> bool:
        message = str(exc).lower()
        if isinstance(exc, TypeError) and ("func_tool" in message or "tool_choice" in message):
            return True
        mentions_tool = "tool" in message or "function call" in message
        unsupported = any(
            token in message
            for token in ("not support", "unsupported", "not enabled", "unknown parameter")
        )
        return mentions_tool and unsupported
