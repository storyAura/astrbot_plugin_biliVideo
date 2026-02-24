import asyncio
import json
import os
from typing import Optional
from urllib.parse import unquote

import aiohttp

from astrbot.api import logger

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.bilibili.com',
}


class BilibiliLogin:
    """B站二维码扫码登录"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.cookies_path = os.path.join(data_dir, "bili_cookies.json")
        self._cookies = self._load_cookies()

    def _load_cookies(self) -> dict:
        """从文件加载已保存的 Cookie"""
        if os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                if cookies.get("SESSDATA"):
                    logger.info("已加载保存的 B站 Cookie")
                    return cookies
            except Exception as e:
                logger.warning(f"加载 Cookie 失败: {e}")
        return {}

    def _save_cookies(self, cookies: dict):
        """保存 Cookie 到文件"""
        with open(self.cookies_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        self._cookies = cookies
        logger.info("B站 Cookie 已保存")

    def get_cookies(self) -> dict:
        """获取当前 Cookie"""
        return self._cookies

    def is_logged_in(self) -> bool:
        """是否已登录"""
        return bool(self._cookies.get("SESSDATA"))

    async def generate_qrcode(self) -> Optional[dict]:
        """
        申请二维码

        :return: {"url": "...", "qrcode_key": "..."} 或 None
        """
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.get(QR_GENERATE_URL, headers=HEADERS) as resp:
                    if resp.status != 200:
                        logger.error(f"申请二维码失败, HTTP {resp.status}")
                        return None

                    data = await resp.json()
                    if data.get("code") != 0:
                        logger.error(f"申请二维码失败: {data.get('message')}")
                        return None

                    return data.get("data")
        except Exception as e:
            logger.error(f"申请二维码异常: {e}")
            return None

    async def poll_login(self, qrcode_key: str) -> dict:
        """
        轮询登录状态

        :param qrcode_key: 二维码 key
        :return: {"status": "waiting/scanned/success/expired", "cookies": {...} or None}
        """
        params = {"qrcode_key": qrcode_key}

        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.get(QR_POLL_URL, params=params, headers=HEADERS) as resp:
                    if resp.status != 200:
                        return {"status": "error", "cookies": None}

                    data = await resp.json()
                    code = data.get("data", {}).get("code")

                    if code == 0:
                        # 登录成功！从 response URL 中提取 cookie
                        url = data["data"].get("url", "")
                        cookies = self._parse_cookies_from_url(url)

                        # 也尝试从 response headers 的 Set-Cookie 获取
                        for cookie in resp.cookies.values():
                            cookies[cookie.key] = cookie.value

                        if cookies.get("SESSDATA"):
                            self._save_cookies(cookies)
                            return {"status": "success", "cookies": cookies}
                        else:
                            return {"status": "error", "cookies": None}

                    elif code == 86090:
                        return {"status": "scanned", "cookies": None}
                    elif code == 86038:
                        return {"status": "expired", "cookies": None}
                    elif code == 86101:
                        return {"status": "waiting", "cookies": None}
                    else:
                        return {"status": "error", "cookies": None}

        except Exception as e:
            logger.error(f"轮询登录状态异常: {e}")
            return {"status": "error", "cookies": None}

    async def do_login_flow(self, qrcode_key: str, timeout: int = 180) -> dict:
        """
        执行完整的登录轮询流程

        :param qrcode_key: 二维码 key
        :param timeout: 超时时间（秒）
        :return: {"status": "success/expired/timeout/error", "cookies": {...} or None}
        """
        elapsed = 0
        interval = 3  # 每3秒轮询一次

        while elapsed < timeout:
            result = await self.poll_login(qrcode_key)

            if result["status"] == "success":
                return result
            elif result["status"] == "expired":
                return result
            elif result["status"] == "error":
                return result

            await asyncio.sleep(interval)
            elapsed += interval

        return {"status": "timeout", "cookies": None}

    @staticmethod
    def _parse_cookies_from_url(url: str) -> dict:
        """从登录成功后的 URL 参数中提取 Cookie"""
        cookies = {}
        if '?' not in url:
            return cookies

        query = url.split('?', 1)[1]
        for param in query.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                if key in ('SESSDATA', 'bili_jct', 'DedeUserID', 'sid'):
                    cookies[key] = unquote(value)

        return cookies

    def logout(self):
        """清除登录状态"""
        self._cookies = {}
        try:
            if os.path.exists(self.cookies_path):
                os.remove(self.cookies_path)
        except OSError as e:
            logger.warning(f"删除 Cookie 文件失败: {e}")
        logger.info("B站登录状态已清除")
