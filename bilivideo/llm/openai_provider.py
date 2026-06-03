"""OpenAI-compatible HTTP LLM provider (DeepSeek, Moonshot, etc.)."""

from __future__ import annotations

import asyncio

import aiohttp

from ..core.exceptions import LLMError, RateLimitError
from ..core.logging import get_logger

logger = get_logger("BiliVideo/LLM/OpenAI")

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=120)


class OpenAICompatibleProvider:
    """POSTs to `<base>/chat/completions` with a Bearer token."""

    def __init__(self, *, api_base: str, api_key: str, model: str, temperature: float) -> None:
        self._url = f"{api_base.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._temperature = temperature

    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
                async with session.post(self._url, json=payload, headers=headers) as resp:
                    body = await resp.text()
                    if resp.status == 429:
                        retry_after_raw = resp.headers.get("Retry-After")
                        try:
                            retry_after = float(retry_after_raw) if retry_after_raw else None
                        except (TypeError, ValueError):
                            retry_after = None
                        raise RateLimitError(retry_after=retry_after)
                    if resp.status != 200:
                        raise LLMError(f"OpenAI HTTP {resp.status}: {body[:200]}")
                    data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"OpenAI response parse error: {exc}") from exc
