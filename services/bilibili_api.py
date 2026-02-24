import uuid
from typing import Optional, List, Dict

import aiohttp

from astrbot.api import logger
from ..utils.wbi_sign import sign_wbi_params

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

BILIBILI_API_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com',
}


def _build_headers(cookies: Optional[dict] = None) -> dict:
    """构建带 Cookie 的请求头"""
    headers = dict(BILIBILI_API_HEADERS)
    cookie_dict = dict(cookies) if cookies else {}
    # B站搜索等 API 需要 buvid3 cookie
    if 'buvid3' not in cookie_dict:
        cookie_dict['buvid3'] = str(uuid.uuid4()) + "infoc"
    cookie_parts = [f'{k}={v}' for k, v in cookie_dict.items() if v]
    if cookie_parts:
        headers['Cookie'] = '; '.join(cookie_parts)
    return headers


async def get_up_info(mid: str, cookies: Optional[dict] = None) -> Optional[Dict]:
    """
    获取 UP主 基本信息

    :param mid: UP主 UID
    :param cookies: B站 cookie dict
    :return: {"mid", "name", "face", "sign"} 或 None
    """
    params = {"mid": mid}
    signed_params = await sign_wbi_params(params, cookies=cookies)

    url = "https://api.bilibili.com/x/space/wbi/acc/info"
    headers = _build_headers(cookies)

    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(url, params=signed_params, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"获取UP主信息失败, HTTP {resp.status}")
                    return None

                data = await resp.json()
                if data.get("code") != 0:
                    logger.warning(f"获取UP主信息失败: code={data.get('code')}, msg={data.get('message')}")
                    return None

                info = data.get("data") or {}
                return {
                    "mid": str(info.get("mid", mid)),
                    "name": info.get("name", "未知"),
                    "face": info.get("face", ""),
                    "sign": info.get("sign", ""),
                }
    except Exception as e:
        logger.error(f"获取UP主信息异常: {e}")
        return None


async def get_latest_videos(mid: str, count: int = 5, cookies: Optional[dict] = None) -> List[Dict]:
    """
    获取 UP主 最新投稿视频列表

    :param mid: UP主 UID
    :param count: 获取数量
    :param cookies: B站 cookie dict
    :return: 视频列表 [{"bvid", "title", "duration", "pubdate", "pic"}]
    """
    params = {
        "mid": mid,
        "ps": count,
        "pn": 1,
        "order": "pubdate",
    }
    signed_params = await sign_wbi_params(params, cookies=cookies)

    url = "https://api.bilibili.com/x/space/wbi/arc/search"
    headers = _build_headers(cookies)

    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(url, params=signed_params, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"获取UP主视频列表失败, HTTP {resp.status}")
                    return []

                data = await resp.json()
                if data.get("code") != 0:
                    logger.warning(f"获取UP主视频列表失败: code={data.get('code')}, msg={data.get('message')}")
                    return []

                vlist = (data.get("data") or {}).get("list") or {}
                vlist = vlist.get("vlist") or []
                result = []
                for v in vlist[:count]:
                    result.append({
                        "bvid": v.get("bvid", ""),
                        "title": v.get("title", ""),
                        "duration": v.get("length", ""),
                        "pubdate": v.get("created", 0),
                        "pic": v.get("pic", ""),
                        "description": v.get("description", ""),
                    })
                return result
    except Exception as e:
        logger.error(f"获取UP主视频列表异常: {e}")
        return []

async def search_up_by_name(keyword: str, cookies: Optional[dict] = None) -> Optional[Dict]:
    """
    通过关键词搜索UP主（返回粉丝最多的第一个）

    :param keyword: 搜索关键词（UP主昵称）
    :param cookies: B站 cookie dict
    :return: {"mid", "name"} 或 None
    """
    # 先尝试 WBI 签名版搜索接口
    params = {
        "search_type": "bili_user",
        "keyword": keyword,
        "page": 1,
        "order": "fans",
        "order_sort": 0,
    }
    signed_params = await sign_wbi_params(params, cookies=cookies)

    url = "https://api.bilibili.com/x/web-interface/wbi/search/type"
    headers = _build_headers(cookies)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=signed_params, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"搜索UP主失败, HTTP {resp.status}")
                    return None

                data = await resp.json()
                code = data.get("code")
                logger.info(f"搜索UP主 '{keyword}' 响应: code={code}, message={data.get('message')}")

                if code != 0:
                    logger.warning(f"搜索UP主失败: code={code}, msg={data.get('message')}")
                    # 回退到旧版搜索接口
                    return await _search_up_fallback(keyword, cookies)

                results = data.get("data", {}).get("result", [])
                if not results:
                    logger.info(f"搜索UP主 '{keyword}' 无结果")
                    return None

                # 优先精确匹配
                for r in results:
                    uname = r.get("uname", "")
                    # B站搜索结果的 uname 可能包含 <em> 高亮标签
                    clean_name = uname.replace("<em class=\"keyword\">", "").replace("</em>", "")
                    if clean_name == keyword:
                        return {
                            "mid": str(r.get("mid", "")),
                            "name": clean_name,
                        }

                # 无精确匹配，返回第一个
                first = results[0]
                uname = first.get("uname", "未知")
                clean_name = uname.replace("<em class=\"keyword\">", "").replace("</em>", "")
                return {
                    "mid": str(first.get("mid", "")),
                    "name": clean_name,
                }
    except Exception as e:
        logger.error(f"搜索UP主异常: {e}", exc_info=True)
        return await _search_up_fallback(keyword, cookies)


async def _search_up_fallback(keyword: str, cookies: Optional[dict] = None) -> Optional[Dict]:
    """旧版搜索接口（不需要 WBI 签名）"""
    url = "https://api.bilibili.com/x/web-interface/search/type"
    params = {
        "search_type": "bili_user",
        "keyword": keyword,
        "page": 1,
        "order": "fans",
    }
    headers = _build_headers(cookies)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"搜索UP主(fallback)失败, HTTP {resp.status}")
                    return None

                data = await resp.json()
                code = data.get("code")
                logger.info(f"搜索UP主(fallback) '{keyword}' 响应: code={code}")

                if code != 0:
                    logger.warning(f"搜索UP主(fallback)失败: {data.get('message')}")
                    return None

                results = data.get("data", {}).get("result", [])
                if not results:
                    return None

                first = results[0]
                uname = first.get("uname", "未知")
                clean_name = uname.replace("<em class=\"keyword\">", "").replace("</em>", "")
                return {
                    "mid": str(first.get("mid", "")),
                    "name": clean_name,
                }
    except Exception as e:
        logger.error(f"搜索UP主(fallback)异常: {e}")
        return None

