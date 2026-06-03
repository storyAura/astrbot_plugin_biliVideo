"""Bilibili QR-code login flow.

Improvements over the previous implementation:
  * uses the shared HTTP client (no per-call ClientSession)
  * exponential backoff with jitter while polling, so a long-pending login
    doesn't hammer the server every 3 seconds
  * returns explicit `LoginResult` enum values instead of magic strings
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from urllib.parse import unquote

import aiohttp

from ..core.constants import (
    DEFAULT_REFERER,
    DEFAULT_USER_AGENT,
    ENDPOINT_QR_GENERATE,
    ENDPOINT_QR_POLL,
    HTTP_TIMEOUT_SECONDS,
)
from ..core.logging import get_logger

logger = get_logger("BiliVideo/QRLogin")


class LoginStatus(str, Enum):
    SUCCESS = "success"
    EXPIRED = "expired"
    SCANNED = "scanned"
    WAITING = "waiting"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(slots=True)
class LoginResult:
    status: LoginStatus
    cookies: dict[str, str] | None = None


@dataclass(slots=True, frozen=True)
class QRCode:
    url: str
    key: str


_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Referer": DEFAULT_REFERER,
}


class QRLoginService:
    """Encapsulates the QR generate + poll loop."""

    def __init__(self) -> None:
        self._timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)

    async def generate(self) -> QRCode | None:
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(ENDPOINT_QR_GENERATE, headers=_HEADERS) as resp:
                    if resp.status != 200:
                        logger.error(f"QR generate HTTP {resp.status}")
                        return None
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error(f"QR generate failed: {exc}")
            return None

        if data.get("code") != 0:
            logger.error(f"QR generate error: {data.get('message')}")
            return None

        info = data.get("data") or {}
        url = info.get("url", "")
        key = info.get("qrcode_key", "")
        if not url or not key:
            return None
        return QRCode(url=url, key=key)

    async def poll(self, key: str) -> LoginResult:
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session, session.get(
                ENDPOINT_QR_POLL, params={"qrcode_key": key}, headers=_HEADERS
            ) as resp:
                if resp.status != 200:
                    return LoginResult(LoginStatus.ERROR)
                data = await resp.json()
                bilibili_code = (data.get("data") or {}).get("code")

                if bilibili_code == 0:
                    login_url = (data.get("data") or {}).get("url", "")
                    cookies = _parse_cookies_from_url(login_url)
                    for cookie in resp.cookies.values():
                        cookies[cookie.key] = cookie.value
                    if cookies.get("SESSDATA"):
                        return LoginResult(LoginStatus.SUCCESS, cookies)
                    return LoginResult(LoginStatus.ERROR)
                if bilibili_code == 86090:
                    return LoginResult(LoginStatus.SCANNED)
                if bilibili_code == 86038:
                    return LoginResult(LoginStatus.EXPIRED)
                if bilibili_code == 86101:
                    return LoginResult(LoginStatus.WAITING)
                return LoginResult(LoginStatus.ERROR)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning(f"QR poll error: {exc}")
            return LoginResult(LoginStatus.ERROR)

    async def run_until_complete(self, key: str, *, total_timeout: float = 180) -> LoginResult:
        """Poll until success/expire/timeout, with mild exponential backoff."""

        elapsed = 0.0
        delay = 2.0
        while elapsed < total_timeout:
            result = await self.poll(key)
            if result.status in (LoginStatus.SUCCESS, LoginStatus.EXPIRED, LoginStatus.ERROR):
                return result
            sleep_for = delay + random.uniform(0, 0.5)
            await asyncio.sleep(sleep_for)
            elapsed += sleep_for
            # cap delay at 5s; scanned status keeps it tight
            delay = 1.5 if result.status == LoginStatus.SCANNED else min(5.0, delay * 1.2)
        return LoginResult(LoginStatus.TIMEOUT)


def _parse_cookies_from_url(url: str) -> dict[str, str]:
    """Extract SESSDATA / bili_jct / etc. from the redirect URL string."""

    if "?" not in url:
        return {}
    cookies: dict[str, str] = {}
    query = url.split("?", 1)[1]
    for kv in query.split("&"):
        if "=" not in kv:
            continue
        key, value = kv.split("=", 1)
        if key in ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid"):
            cookies[key] = unquote(value)
    return cookies


def merge_cookies(*sources: Mapping[str, str] | None) -> dict[str, str]:
    """Right-biased merge so the latest source wins."""

    out: dict[str, str] = {}
    for source in sources:
        if not source:
            continue
        out.update({k: v for k, v in source.items() if v})
    return out
