"""Pure URL / BV / UID extraction utilities.

These functions are deterministic and do not perform network IO. The async
short-URL resolver lives separately so the synchronous helpers stay 100%
testable in isolation.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Iterable

from ..core.constants import (
    BILI_DOMAINS,
    BV_REGEX,
    LONG_URL_REGEX,
    QQDOC_URL_REGEX,
    SHORT_URL_REGEX,
    UID_REGEX,
)

_TRAILING_URL_CHARS = "\"'`}>]),，。)、）！!？?；;：:"
SHORT_URL_DOMAINS = ("b23.tv", "bili2233.cn", "bili22.cn", "bili23.cn", "bili33.cn")
GENERIC_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)

# ──────────────────────────── basic ────────────────────────────────


def detect_platform(url: str) -> str | None:
    """Return 'bilibili' / 'youtube' / 'douyin' / None.

    Matches the previous behavior so callers don't need to change.
    """

    if not url:
        return None
    try:
        host = urllib.parse.urlparse(_clean_url_token(url)).hostname or ""
    except ValueError:
        return None
    host = host.lower().rstrip(".")
    if any(host == d or host.endswith("." + d) for d in BILI_DOMAINS):
        return "bilibili"
    if host in {"youtu.be", "youtube.com"} or host.endswith(".youtube.com"):
        return "youtube"
    if (
        host == "douyin.com"
        or host.endswith(".douyin.com")
        or host == "tiktok.com"
        or host.endswith(".tiktok.com")
    ):
        return "douyin"
    return None


def is_bilibili_domain(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in BILI_DOMAINS)


def extract_bvid(text: str) -> str | None:
    if not text:
        return None
    match = BV_REGEX.search(text)
    return match.group(0) if match else None


def extract_uid(text: str) -> str | None:
    """Extract a Bilibili UID from a raw UID, space link, or other text."""

    if not text:
        return None
    text = text.strip()
    if text.isdigit():
        return text
    match = UID_REGEX.search(text)
    return match.group(1) if match else None


def extract_long_url(text: str) -> str | None:
    if not text:
        return None
    match = LONG_URL_REGEX.search(text)
    return _clean_url_token(match.group(0)) if match else None


def extract_short_url(text: str) -> str | None:
    if not text:
        return None
    match = SHORT_URL_REGEX.search(text)
    if match is None:
        return None
    return _clean_url_token(match.group(0))


def extract_url(text: str) -> str | None:
    """Extract the first generic http(s) URL from chat text."""

    if not text:
        return None
    match = GENERIC_URL_RE.search(text)
    return _clean_url_token(match.group(0)) if match else None


def _clean_url_token(url: str) -> str:
    """Strip chat punctuation commonly attached to pasted URLs."""

    return (url or "").strip().strip("<>").rstrip(_TRAILING_URL_CHARS)


def is_short_bili_url(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(_clean_url_token(url)).hostname or ""
    except ValueError:
        return False
    host = host.lower().rstrip(".")
    return host in SHORT_URL_DOMAINS


# ──────────────────────────── JSON cards ───────────────────────────


def find_qqdoc_url(payload: object) -> str | None:
    """Recursively search a JSON-card structure for a Bilibili `qqdocurl`.

    QQ mini-app cards nest the actual URL under `meta.<provider>.qqdocurl`.
    Returns the first Bilibili-domain URL we encounter.
    """

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in ("qqdocurl", "jumpUrl", "url") and isinstance(value, str):
                if is_bilibili_domain(value):
                    return value
            found = find_qqdoc_url(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_qqdoc_url(item)
            if found:
                return found
    return None


def parse_json_card(text: str) -> str | None:
    """Try to parse `text` as JSON and locate a Bilibili URL inside."""

    if not text:
        return None
    text = text.strip()
    if not text.startswith("{") and not text.startswith("["):
        # also try the regex shortcut for embedded `qqdocurl` strings
        match = QQDOC_URL_REGEX.search(text)
        if match and is_bilibili_domain(match.group(1)):
            return match.group(1)
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = QQDOC_URL_REGEX.search(text)
        if match and is_bilibili_domain(match.group(1)):
            return match.group(1)
        return None
    return find_qqdoc_url(payload)


def parse_cq_json(raw: str) -> str | None:
    """Decode a `[CQ:json,data=...]` segment and search inside it."""

    if not raw or "[CQ:json" not in raw:
        return None
    match = re.search(r"\[CQ:json,data=(.*?)\]", raw, re.DOTALL)
    if not match:
        return None
    payload = (
        match.group(1)
        .replace("&amp;", "&")
        .replace("&#44;", ",")
        .replace("&#91;", "[")
        .replace("&#93;", "]")
    )
    return parse_json_card(payload)


# ──────────────────────────── pipeline ─────────────────────────────


def collect_candidates(*texts: str | None) -> list[str]:
    """Concatenate non-empty inputs into a single search string."""

    return [t for t in texts if isinstance(t, str) and t]


def first_present(items: Iterable[str | None]) -> str | None:
    for item in items:
        if item:
            return item
    return None
