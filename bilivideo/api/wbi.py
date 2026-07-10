"""WBI signing for Bilibili web APIs.

The original implementation kept the mixin_key in a module-level tuple,
which is racy if two coroutines try to refresh simultaneously. Here we
delegate locking to an `LRUTTLCache` so a single in-flight fetch is shared
by all callers and stale keys expire automatically.
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from collections.abc import Mapping
from typing import TYPE_CHECKING

from ..cache.lru_ttl import LRUTTLCache
from ..core.constants import ENDPOINT_NAV, WBI_CACHE_TTL_SECONDS
from ..core.exceptions import NetworkError
from ..core.logging import get_logger

if TYPE_CHECKING:
    from .client import BilibiliHTTPClient

logger = get_logger("BiliVideo/WBI")


# 64-element table baked into Bilibili's web client. Do not change.
_MIXIN_TABLE: tuple[int, ...] = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)

_KEY_CACHE: LRUTTLCache[str, str] = LRUTTLCache(max_size=2, ttl_seconds=WBI_CACHE_TTL_SECONDS)
_KEY_CACHE_KEY = "mixin_key"


async def clear_wbi_cache() -> None:
    await _KEY_CACHE.clear()


def _derive_mixin_key(img_key: str, sub_key: str) -> str:
    orig = img_key + sub_key
    return "".join(orig[i] for i in _MIXIN_TABLE)[:32]


async def _fetch_mixin_key(client: BilibiliHTTPClient) -> str:
    """Hit /x/web-interface/nav via the shared client and derive a fresh mixin_key.

    Reuses the plugin-wide connection pool instead of a throwaway session.
    Nav returns the wbi keys even when not logged in (with a non-zero code),
    so the response `code` is deliberately not enforced.
    """

    payload = await client.request_json("GET", ENDPOINT_NAV, expect_code_zero=False)
    wbi_img = (payload.get("data") or {}).get("wbi_img") or {}
    img_url = wbi_img.get("img_url", "")
    sub_url = wbi_img.get("sub_url", "")
    if not img_url or not sub_url:
        raise NetworkError("WBI nav missing img_url/sub_url")

    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    mixin = _derive_mixin_key(img_key, sub_key)
    logger.info("WBI mixin_key refreshed")
    return mixin


async def get_mixin_key(client: BilibiliHTTPClient) -> str:
    """Return a cached mixin_key, refreshing once per TTL across coroutines."""

    return await _KEY_CACHE.get_or_set(_KEY_CACHE_KEY, lambda: _fetch_mixin_key(client))


async def sign_params(
    params: Mapping[str, object],
    *,
    client: BilibiliHTTPClient,
) -> dict[str, object]:
    """Return a copy of `params` augmented with `wts` and `w_rid`.

    On WBI fetch failure we **return the original parameters unchanged** so
    the caller can fall back to the unsigned variant of the API. This mirrors
    Bilibili's leniency on a few endpoints.
    """

    signed: dict[str, object] = dict(params)
    try:
        mixin_key = await get_mixin_key(client)
    except NetworkError as exc:
        logger.warning(f"WBI sign skipped, falling back unsigned: {exc}")
        return signed

    signed["wts"] = int(time.time())
    sorted_params = dict(sorted(signed.items()))
    query = urllib.parse.urlencode(sorted_params)
    for ch in "!'()*":
        query = query.replace(urllib.parse.quote(ch), "")
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return signed
