"""LLM provider factory tests."""

from __future__ import annotations

import pytest

from bilivideo.core.config import PluginConfig
from bilivideo.core.exceptions import LLMError
from bilivideo.llm.provider import DisabledLLMProvider, build_provider


@pytest.mark.asyncio
async def test_openai_compatible_without_credentials_is_disabled() -> None:
    cfg = PluginConfig.from_mapping({"llm_provider": "openai_compatible"})
    provider = build_provider(cfg, astrbot_context=None)

    assert isinstance(provider, DisabledLLMProvider)
    with pytest.raises(LLMError) as exc:
        await provider.chat("hello")
    assert "AI 未配置" in exc.value.user_message
