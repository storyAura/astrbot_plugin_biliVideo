"""AstrbotProvider provider-selection tests."""

from __future__ import annotations

import pytest

from bilivideo.core.exceptions import LLMError
from bilivideo.llm.astrbot_provider import AstrbotProvider


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
