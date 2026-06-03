"""LLM provider that delegates to AstrBot's configured Provider."""

from __future__ import annotations

from ..core.exceptions import LLMError
from ..core.logging import get_logger

logger = get_logger("BiliVideo/LLM/AstrBot")


class AstrbotProvider:
    """Calls `context.get_using_provider().text_chat()`.

    The AstrBot framework hands us a `Context` object; we keep a weak
    handle so the provider object stays in sync with whatever the user
    selected in the AstrBot dashboard.
    """

    def __init__(self, astrbot_context: object | None, provider_id: str = "") -> None:
        self._context = astrbot_context
        self.provider_id = provider_id

    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
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
        try:
            response = await provider.text_chat(
                prompt=prompt,
                session_id=session_id or "BiliVideo_plugin",
            )
        except Exception as exc:  # pragma: no cover - relies on AstrBot
            raise LLMError(f"AstrBot text_chat failed: {exc}") from exc

        if hasattr(response, "completion_text"):
            return str(response.completion_text or "").strip()
        if isinstance(response, str):
            return response.strip()
        return str(response).strip()
