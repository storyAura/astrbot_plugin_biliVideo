"""
B站 WBI 签名工具

用于对 B站 WBI API 请求参数进行签名。
"""

import hashlib
import logging
import time
import urllib.parse
from typing import Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# WBI 混淆表 (固定)
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

# 缓存 mixin_key
_wbi_cache: Optional[Tuple[str, float]] = None  # (mixin_key, fetch_time)
_WBI_CACHE_TTL = 86400  # 24h

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"


def _get_mixin_key(img_key: str, sub_key: str) -> str:
    """通过 img_key 和 sub_key 生成 mixin_key"""
    orig = img_key + sub_key
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


async def _fetch_wbi_keys(cookies: Optional[dict] = None) -> Optional[str]:
    """从 B站 nav 接口获取 img_key + sub_key，生成 mixin_key"""
    global _wbi_cache

    # 检查缓存
    if _wbi_cache:
        mixin_key, fetch_time = _wbi_cache
        if time.time() - fetch_time < _WBI_CACHE_TTL:
            return mixin_key

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com',
    }
    if cookies:
        parts = [f'{k}={v}' for k, v in cookies.items() if v]
        if parts:
            headers['Cookie'] = '; '.join(parts)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(NAV_URL, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"获取 WBI keys 失败, HTTP {resp.status}")
                    return None

                data = await resp.json()
                wbi_img = data.get("data", {}).get("wbi_img", {})
                img_url = wbi_img.get("img_url", "")
                sub_url = wbi_img.get("sub_url", "")

                if not img_url or not sub_url:
                    logger.warning("WBI img_url 或 sub_url 为空")
                    return None

                # 从 URL 中提取 key: 取最后一个 / 后的文件名，去掉 .wbi 后缀
                img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
                sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]

                mixin_key = _get_mixin_key(img_key, sub_key)
                _wbi_cache = (mixin_key, time.time())
                logger.info("WBI mixin_key 已更新")
                return mixin_key

    except Exception as e:
        logger.error(f"获取 WBI keys 异常: {e}")
        return None


async def sign_wbi_params(
    params: dict,
    cookies: Optional[dict] = None,
) -> dict:
    """
    对请求参数进行 WBI 签名，返回添加了 w_rid 和 wts 的新参数字典。

    :param params: 原始请求参数
    :param cookies: B站 cookie (用于获取 mixin_key)
    :return: 签名后的参数字典
    """
    mixin_key = await _fetch_wbi_keys(cookies)
    if not mixin_key:
        logger.warning("无法获取 WBI mixin_key，跳过签名")
        return params

    # 添加 wts
    signed = dict(params)
    signed["wts"] = int(time.time())

    # 按 key 字典序排列
    sorted_params = dict(sorted(signed.items()))

    # 过滤特殊字符 (!'()*)
    query = urllib.parse.urlencode(sorted_params)
    for ch in "!'()*":
        query = query.replace(urllib.parse.quote(ch), "")

    # 计算 w_rid = md5(query + mixin_key)
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    signed["w_rid"] = w_rid

    return signed
