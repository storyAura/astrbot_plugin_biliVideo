"""LLM provider abstraction.

Concrete implementations live in `astrbot_provider.py` and
`openai_provider.py`. The factory in this module picks one based on the
`PluginConfig.llm_provider` field, so the rest of the plugin only deals
with the protocol.
"""

from __future__ import annotations

from typing import Protocol

from ..core.config import PluginConfig
from ..core.exceptions import LLMError


class LLMProvider(Protocol):
    """Async interface for any LLM backend."""

    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
        ...


class DisabledLLMProvider:
    """Provider placeholder used when startup should continue without LLM."""

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message

    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
        raise LLMError("LLM provider disabled", user_message=self.user_message)


def build_provider(
    config: PluginConfig, *, astrbot_context: object | None, provider_id: str = ""
) -> LLMProvider:
    """Return a concrete provider instance based on the config."""

    if config.is_openai_compatible:
        from .openai_provider import OpenAICompatibleProvider

        if not config.has_llm_credentials():
            return DisabledLLMProvider(
                "❌ AI 未配置:请填写 llm_api_base 和 llm_api_key,或切回 AstrBot 内置 LLM"
            )
        return OpenAICompatibleProvider(
            api_base=config.llm_api_base,
            api_key=config.llm_api_key,
            model=config.llm_model,
            temperature=config.llm_temperature,
        )

    from .astrbot_provider import AstrbotProvider

    return AstrbotProvider(astrbot_context, provider_id=provider_id)
