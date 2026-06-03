"""`/B站登录` and `/B站登出` handlers."""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from ..access.control import is_allowed
from ..auth.qrlogin import LoginStatus
from ..services import BiliVideoServices

# Lazy import (test environments lack AstrBot)
try:
    from astrbot.api.message_components import Image, Plain  # type: ignore[import]
except Exception:  # pragma: no cover
    Image = Plain = None  # type: ignore[assignment]


async def handle_login(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    if services.is_logged_in():
        yield event.plain_result("✅ B站已登录,如需重新登录请先 /B站登出")  # type: ignore[attr-defined]
        return

    yield event.plain_result("🔄 正在生成B站登录二维码...")  # type: ignore[attr-defined]

    qr = await services.qrlogin.generate()
    if qr is None:
        yield event.plain_result("❌ 生成二维码失败,请稍后重试")  # type: ignore[attr-defined]
        return

    qr_path = Path(services.data_dir) / f"login_qr_{uuid.uuid4().hex[:8]}.png"
    try:
        import segno

        segno.make(qr.url).save(str(qr_path), scale=10, border=4)
    except ImportError:
        yield event.plain_result("❌ 缺少 segno 依赖,请运行: pip install segno")  # type: ignore[attr-defined]
        return
    except Exception as exc:
        yield event.plain_result(f"❌ 生成二维码图片失败: {exc}")  # type: ignore[attr-defined]
        return

    chain = [
        Plain("📱 请使用B站App扫描下方二维码登录\n⏳ 二维码有效期 3 分钟\n"),
        Image.fromFileSystem(str(qr_path)),
    ]
    yield event.chain_result(chain)  # type: ignore[attr-defined]

    result = await services.qrlogin.run_until_complete(qr.key, total_timeout=180)

    if result.status == LoginStatus.SUCCESS and result.cookies:
        services.update_cookies(result.cookies)
        yield event.plain_result("✅ B站登录成功!")  # type: ignore[attr-defined]
    elif result.status == LoginStatus.EXPIRED:
        yield event.plain_result("⏰ 二维码已过期,请重新发送 /B站登录")  # type: ignore[attr-defined]
    elif result.status == LoginStatus.TIMEOUT:
        yield event.plain_result("⏰ 登录超时,请重新发送 /B站登录")  # type: ignore[attr-defined]
    else:
        yield event.plain_result("❌ 登录失败,请重新发送 /B站登录")  # type: ignore[attr-defined]

    with contextlib.suppress(OSError):
        os.remove(qr_path)


async def handle_logout(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    if not services.is_logged_in():
        yield event.plain_result("ℹ️ 当前未登录B站")  # type: ignore[attr-defined]
        return

    services.update_cookies(None)
    yield event.plain_result("✅ 已退出B站登录")  # type: ignore[attr-defined]
