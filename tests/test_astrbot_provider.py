"""AstrbotProvider provider-selection tests."""

from __future__ import annotations

from typing import Any

import pytest

from bilivideo.core.exceptions import LLMError
from bilivideo.llm.astrbot_provider import AstrbotProvider
from bilivideo.llm.structured_summary import SUMMARY_TOOL_NAME


class _FakeResponse:
    def __init__(self, completion_text: str) -> None:
        self.completion_text = completion_text


class _FakeProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.calls: list[dict[str, str | None]] = []

    async def text_chat(self, *, prompt: str, session_id: str | None = None) -> _FakeResponse:
        self.calls.append({"prompt": prompt, "session_id": session_id})
        return _FakeResponse(self.provider_id)


class _FakeContext:
    def __init__(self, current: _FakeProvider, by_id: dict[str, _FakeProvider]) -> None:
        self._current = current
        self._by_id = by_id

    def get_using_provider(self) -> _FakeProvider:
        return self._current

    def get_provider_by_id(self, provider_id: str) -> _FakeProvider | None:
        return self._by_id.get(provider_id)


@pytest.mark.asyncio
async def test_empty_provider_id_uses_using_provider() -> None:
    current = _FakeProvider("current")
    context = _FakeContext(current, {"X": _FakeProvider("X")})

    provider = AstrbotProvider(context)
    answer = await provider.chat("hello")

    assert answer == "current"
    assert current.calls == [{"prompt": "hello", "session_id": "BiliVideo_plugin"}]


@pytest.mark.asyncio
async def test_known_provider_id_uses_provider_by_id() -> None:
    current = _FakeProvider("current")
    target = _FakeProvider("X")
    context = _FakeContext(current, {"X": target})

    provider = AstrbotProvider(context, provider_id="X")
    answer = await provider.chat("hello")

    assert answer == "X"
    assert target.calls == [{"prompt": "hello", "session_id": "BiliVideo_plugin"}]
    assert current.calls == []


@pytest.mark.asyncio
async def test_missing_provider_id_falls_back_to_using_provider() -> None:
    current = _FakeProvider("current")
    context = _FakeContext(current, {"X": _FakeProvider("X")})

    provider = AstrbotProvider(context, provider_id="missing")
    answer = await provider.chat("hello")

    assert answer == "current"
    assert current.calls == [{"prompt": "hello", "session_id": "BiliVideo_plugin"}]


@pytest.mark.asyncio
async def test_none_context_raises_llm_error() -> None:
    provider = AstrbotProvider(None)

    with pytest.raises(LLMError):
        await provider.chat("hello")


class _FakeFunctionTool:
    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs["name"]
        self.parameters = kwargs["parameters"]


class _FakeToolSet:
    def __init__(self, tools: list[_FakeFunctionTool]) -> None:
        self.tools = tools


class _StructuredProvider:
    def __init__(
        self,
        response: object | None = None,
        *,
        modalities: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.provider_config = {"modalities": modalities or []}
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def text_chat(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response or _FakeResponse("")

    def get_model(self) -> str:
        return "test-model"


class _ToolResponse(_FakeResponse):
    def __init__(
        self,
        *,
        names: list[str] | None = None,
        arguments: list[dict[str, object]] | None = None,
        text: str = "",
    ) -> None:
        super().__init__(text)
        self.tools_call_name = names or []
        self.tools_call_args = arguments or []


def _enable_fake_tools(monkeypatch) -> None:
    monkeypatch.setattr("bilivideo.llm.astrbot_provider.FunctionTool", _FakeFunctionTool)
    monkeypatch.setattr("bilivideo.llm.astrbot_provider.ToolSet", _FakeToolSet)


@pytest.mark.asyncio
async def test_structured_summary_requires_single_astrbot_tool(monkeypatch) -> None:
    _enable_fake_tools(monkeypatch)
    payload = {
        "title": "标题",
        "chapters": [
            {"title": "章节", "timestamp_seconds": 0, "body_markdown": "内容"}
        ],
    }
    current = _StructuredProvider(
        _ToolResponse(names=[SUMMARY_TOOL_NAME], arguments=[payload]),
        modalities=["text", "tool_use"],
    )
    provider = AstrbotProvider(_FakeContext(current, {}))  # type: ignore[arg-type]

    attempt = await provider.chat_structured_summary("prompt", include_ai_summary=False)

    assert attempt.arguments == payload
    assert len(current.calls) == 1
    assert current.calls[0]["tool_choice"] == "required"
    tool_set = current.calls[0]["func_tool"]
    assert isinstance(tool_set, _FakeToolSet)
    assert [tool.name for tool in tool_set.tools] == [SUMMARY_TOOL_NAME]
    assert tool_set.tools[0].parameters["additionalProperties"] is False


@pytest.mark.asyncio
async def test_explicitly_unsupported_modality_skips_tool_request(monkeypatch) -> None:
    _enable_fake_tools(monkeypatch)
    current = _StructuredProvider(modalities=["text"])
    provider = AstrbotProvider(_FakeContext(current, {}))  # type: ignore[arg-type]

    attempt = await provider.chat_structured_summary("prompt", include_ai_summary=True)

    assert attempt.arguments is None
    assert attempt.fallback_text == ""
    assert current.calls == []


@pytest.mark.asyncio
async def test_unsupported_tool_error_is_cached_per_model(monkeypatch) -> None:
    _enable_fake_tools(monkeypatch)
    current = _StructuredProvider(error=TypeError("unexpected keyword argument 'func_tool'"))
    provider = AstrbotProvider(_FakeContext(current, {}))  # type: ignore[arg-type]

    first = await provider.chat_structured_summary("prompt", include_ai_summary=True)
    second = await provider.chat_structured_summary("prompt", include_ai_summary=True)

    assert first.arguments is None
    assert second.arguments is None
    assert len(current.calls) == 1


@pytest.mark.asyncio
async def test_plain_response_from_tool_request_is_reused_as_fallback(monkeypatch) -> None:
    _enable_fake_tools(monkeypatch)
    current = _StructuredProvider(_ToolResponse(text="# 普通 Markdown"))
    provider = AstrbotProvider(_FakeContext(current, {}))  # type: ignore[arg-type]

    attempt = await provider.chat_structured_summary("prompt", include_ai_summary=True)

    assert attempt.arguments is None
    assert attempt.fallback_text == "# 普通 Markdown"
