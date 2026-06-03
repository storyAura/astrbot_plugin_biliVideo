"""`/YT登录` and `/YT登出` handlers — interactive YouTube cookie login.

YouTube has no QR/scan login that yt-dlp can drive, so the credential is a
cookies jar. Mirroring `/B站登录`, the whole flow happens in chat: the user
pastes the cookies their browser exported and the bot saves them itself, so a
VPS user never has to create a file on the server. Includes a strong
burner-account ban warning, since pulling YouTube from a datacenter IP is risky.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..access.control import is_allowed
from ..services import BiliVideoServices
from ._utils import parse_command_args


def _instructions(services: BiliVideoServices) -> str:
    logged_in = "✅ 已登录(已保存 cookies)" if services.youtube_cookies.has() else "❌ 未登录"
    multi = (
        "✅ 已开启"
        if services.config.enable_multi_platform
        else "❌ 未开启(配置→🧪 实验功能→「多平台」)"
    )
    return (
        "📺 YouTube 登录(实验)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 多平台开关: {multi}\n"
        f"🍪 登录状态: {logged_in}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "YouTube 没有扫码登录,需要用 cookies。整个过程在聊天里完成,\n"
        "机器人会自动保存,你无需在服务器上建任何文件。\n\n"
        "📌 步骤:\n"
        "1. 在你自己电脑的浏览器登录 youtube.com(建议用小号)\n"
        "2. 装扩展「Get cookies.txt LOCALLY」,导出 youtube.com 的 cookies.txt\n"
        "3. 把内容直接贴在命令后面发给我:\n"
        "   /YT登录 <把 cookies 粘贴到这里>\n"
        "   (也支持 `名称=值; 名称=值` 形式)\n\n"
        "🔒 建议私聊使用,避免 cookies 泄漏。\n"
        "⚠️ yt-dlp 从机房 IP 拉 YouTube 有封号风险,请务必用小号 / 不重要的 Google 账号!\n"
        "退出登录:/YT登出"
    )


async def handle_youtube_login(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    payload = parse_command_args(getattr(event, "message_str", "") or "")
    if not payload:
        yield event.plain_result(_instructions(services))  # type: ignore[attr-defined]
        return

    count = services.youtube_cookies.save(payload)
    if count:
        yield event.plain_result(  # type: ignore[attr-defined]
            f"✅ 已保存 YouTube cookies(共 {count} 条)。\n"
            "开启🧪 多平台后即可 /总结 YouTube 链接。\n"
            "⚠️ 提醒:请确认用的是小号,机房 IP 拉流有封号风险。"
        )
    else:
        yield event.plain_result(  # type: ignore[attr-defined]
            "❌ 没认出 cookies 格式。\n"
            "请粘贴浏览器导出的 cookies.txt(Netscape 格式),"
            "或 `名称=值; 名称=值` 形式。\n发送 /YT登录 查看完整步骤。"
        )


async def handle_youtube_logout(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
        yield event.plain_result("⛔ 你没有权限使用此插件")  # type: ignore[attr-defined]
        return

    if not services.youtube_cookies.has():
        yield event.plain_result("ℹ️ 当前没有保存 YouTube cookies")  # type: ignore[attr-defined]
        return

    services.youtube_cookies.clear()
    yield event.plain_result("✅ 已清除 YouTube cookies")  # type: ignore[attr-defined]
