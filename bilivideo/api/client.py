"""Bilibili HTTP client.

Replaces the previous code that created a brand-new `aiohttp.ClientSession`
on every API call. Session-level connection reuse cuts overhead, and a thin
retry layer makes the plugin robust against transient B 站 network blips.
"""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

import aiohttp

from ..core.constants import (
    DEFAULT_REFERER,
    DEFAULT_USER_AGENT,
    ESSENTIAL_COOKIES,
    HTTP_BACKOFF_BASE,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT_SECONDS,
)
from ..core.exceptions import BilibiliAPIError, NetworkError, RiskControlError
from ..core.logging import get_logger

logger = get_logger("BiliVideo/HTTP")


def _build_cookie_header(cookies: Mapping[str, str] | None) -> dict[str, str]:
    """Inject mandatory cookies (e.g. buvid3) so the search API works even
    before the user logs in."""

    cookie_dict: dict[str, str] = dict(cookies) if cookies else {}
    for required in ESSENTIAL_COOKIES:
        if required not in cookie_dict:
            cookie_dict[required] = f"{uuid.uuid4()}infoc"
    parts = [f"{k}={v}" for k, v in cookie_dict.items() if v]
    return {"Cookie": "; ".join(parts)} if parts else {}


def _base_headers(cookies: Mapping[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": DEFAULT_REFERER,
    }
    headers.update(_build_cookie_header(cookies))
    return headers


class BilibiliHTTPClient:
    """Thin async client around `aiohttp.ClientSession`.

    Maintains a single session for the lifetime of the plugin. The class is
    intentionally small; specialized API calls live in `endpoints.py` and use
    this client through dependency injection.
    """

    def __init__(self, cookies: Mapping[str, str] | None = None) -> None:
        self._cookies: dict[str, str] = dict(cookies) if cookies else {}
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # session lifecycle
    # ------------------------------------------------------------------
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        async with self._lock:
            if self._session is None or self._session.closed:
                timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
                connector = aiohttp.TCPConnector(limit=16, ttl_dns_cache=300)
                self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            return self._session

    async def close(self) -> None:
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    def update_cookies(self, cookies: Mapping[str, str] | None) -> None:
        self._cookies = dict(cookies) if cookies else {}

    @property
    def cookies(self) -> Mapping[str, str]:
        return self._cookies

    # ------------------------------------------------------------------
    # core request primitive
    # ------------------------------------------------------------------
    async def request_json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        json_body: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        expect_code_zero: bool = True,
    ) -> dict[str, object]:
        """Issue a JSON request with retries, returning the parsed payload.

        When `expect_code_zero` is true, raises `BilibiliAPIError` if the
        response carries a non-zero `code`.
        """

        merged_headers = _base_headers(self._cookies)
        if headers:
            merged_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(1, HTTP_MAX_RETRIES + 1):
            try:
                payload = await self._do_request(
                    method, url, params=params, json_body=json_body, headers=merged_headers
                )
                if expect_code_zero and isinstance(payload, dict):
                    code = payload.get("code")
                    if isinstance(code, int) and code != 0:
                        if code in (-412, 412, -352):
                            raise RiskControlError(
                                f"Bilibili risk control (code={code}): {payload.get('message', '')}"
                            )
                        raise BilibiliAPIError(code, str(payload.get("message", "")))
                return payload
            except (asyncio.TimeoutError, aiohttp.ClientError, NetworkError) as exc:
                last_error = exc
                if attempt == HTTP_MAX_RETRIES:
                    break
                # Add jitter so concurrent retries don't synchronize.
                delay = HTTP_BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 0.2)
                logger.warning(
                    f"HTTP {method} {url} attempt {attempt} failed: {exc}; retry in {delay:.2f}s"
                )
                await asyncio.sleep(delay)
            except BilibiliAPIError:
                raise
            except RiskControlError:
                raise
            except json.JSONDecodeError as exc:
                last_error = exc
                break

        raise NetworkError(f"{method} {url} failed: {last_error}")

    async def follow_redirect(self, url: str) -> str | None:
        """Resolve a short URL by following redirects, returning the final URL.

        Deliberately sends NO auth cookies (SESSDATA): resolving a redirect
        needs no login, and the target host is not always trusted, so the
        session credential must never leak to it.
        """

        session = await self._ensure_session()
        try:
            async with session.get(
                url, headers=_base_headers(None), allow_redirects=True
            ) as resp:
                return str(resp.url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning(f"follow_redirect({url}) failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------
    async def _do_request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, object] | None,
        json_body: Mapping[str, object] | None,
        headers: Mapping[str, str],
    ) -> dict[str, object]:
        session = await self._ensure_session()
        async with session.request(
            method,
            url,
            params=dict(params) if params else None,
            json=dict(json_body) if json_body else None,
            headers=dict(headers),
        ) as resp:
            text = await resp.text()
            if resp.status >= 500:
                raise NetworkError(f"server {resp.status}")
            if resp.status >= 400:
                raise NetworkError(f"client {resp.status}")
            try:
                return json.loads(text) if text else {}
            except json.JSONDecodeError as exc:
                raise NetworkError(f"bad JSON from {url}: {exc}") from exc

    # convenience context manager (for tests / one-off use) -----------
    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[BilibiliHTTPClient]:
        try:
            await self._ensure_session()
            yield self
        finally:
            await self.close()
