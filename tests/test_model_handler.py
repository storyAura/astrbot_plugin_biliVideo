"""Tests for the /总结模型 handler (built-in model listing/switching)."""

from __future__ import annotations

import pytest

from bilivideo.core.config import PluginConfig
from bilivideo.handlers.model import handle_model


class _Event:
    def __init__(self, message_str: str = "") -> None:
        self.unified_msg_origin = "aiocqhttp:GroupMessage:1"
        self.message_str = message_str

    def plain_result(self, text: str) -> str:
        return text


class _Meta:
    def __init__(self, pid: str) -> None:
        self.id = pid


class _Provider:
    def __init__(self, pid: str, model: str) -> None:
        self._pid = pid
        self._model = model

    def meta(self) -> _Meta:
        return _Meta(self._pid)

    def get_model(self) -> str:
        return self._model


class _Context:
    def __init__(self, providers: list[_Provider]) -> None:
        self._providers = providers

    def get_all_providers(self) -> list[_Provider]:
        return self._providers


class _LLM:
    def __init__(self) -> None:
        self.provider_id = ""


class _RuntimeState:
    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def set_str(self, key: str, value: str) -> None:
        self.saved[key] = value


class _Services:
    def __init__(self, config: PluginConfig, providers: list[_Provider]) -> None:
        self.config = config
        self.astrbot_context = _Context(providers)
        self.llm = _LLM()
        self.runtime_state = _RuntimeState()


async def _collect(agen) -> list[str]:
    return [item async for item in agen]


def _astrbot_services(providers: list[_Provider]) -> _Services:
    return _Services(PluginConfig.from_mapping({"llm_provider": "astrbot"}), providers)


@pytest.mark.asyncio
async def test_no_arg_lists_models() -> None:
    services = _astrbot_services([_Provider("openai_gpt4o", "gpt-4o"), _Provider("ds", "deepseek-chat")])
    out = await _collect(handle_model(services, _Event("/总结模型")))  # type: ignore[arg-type]
    assert "可用内置模型" in out[0]
    assert "openai_gpt4o" in out[0]
    assert "ds" in out[0]


@pytest.mark.asyncio
async def test_switch_to_valid_id() -> None:
    services = _astrbot_services([_Provider("ds", "deepseek-chat")])
    out = await _collect(handle_model(services, _Event("/总结模型 ds")))  # type: ignore[arg-type]
    assert services.llm.provider_id == "ds"
    assert services.runtime_state.saved.get("llm_provider_id") == "ds"
    assert "已切换" in out[0]


@pytest.mark.asyncio
async def test_invalid_id_is_rejected_and_lists() -> None:
    services = _astrbot_services([_Provider("ds", "deepseek-chat")])
    out = await _collect(handle_model(services, _Event("/总结模型 nope")))  # type: ignore[arg-type]
    assert services.llm.provider_id == ""  # unchanged
    assert "未找到" in out[0]


@pytest.mark.asyncio
async def test_reset_restores_default() -> None:
    services = _astrbot_services([_Provider("ds", "deepseek-chat")])
    services.llm.provider_id = "ds"
    out = await _collect(handle_model(services, _Event("/总结模型 默认")))  # type: ignore[arg-type]
    assert services.llm.provider_id == ""
    assert services.runtime_state.saved.get("llm_provider_id") == ""
    assert "默认" in out[0]


@pytest.mark.asyncio
async def test_openai_mode_is_not_applicable() -> None:
    config = PluginConfig.from_mapping(
        {"llm_provider": "openai_compatible", "llm_api_base": "https://x/v1", "llm_api_key": "k"}
    )
    services = _Services(config, [_Provider("ds", "deepseek-chat")])
    out = await _collect(handle_model(services, _Event("/总结模型")))  # type: ignore[arg-type]
    assert "openai_compatible" in out[0]
