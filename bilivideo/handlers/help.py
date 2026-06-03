"""`/总结帮助` handler."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..services import BiliVideoServices

HELP_TEMPLATE = """\
📝 biliVideo 视频总结助手 v2.0
━━━━━━━━━━━━━━━━━━━
🔐 B站登录状态: {login_status}

📌 登录命令:
  /B站登录 (bvlogin) → 扫码登录B站
  /B站登出 (bvlogout) → 退出B站登录
  /YT登录 (ytlogin) → YouTube 登录(贴 cookies,实验)
  /YT登出 (ytlogout) → 清除 YouTube cookies

📌 基本命令:
  /总结 (bv) <{platform_scope}视频链接或BV号>
  /最新视频 (latest) <UP主UID、空间链接或昵称>

📌 订阅管理:
  /订阅 (sub) <UP主UID或昵称>
  /取消订阅 (unsub) <UP主UID或昵称>
  /订阅列表 (sublist/subs)
  /检查更新 (check)

📌 推送目标:
  /添加推送群 (addpg) <群号>
  /添加推送号 (addpu) <QQ号>
  /推送列表 (pushls)
  /移除推送 (rmpush) <群号或QQ号>

📌 自动识别:
  /识别开关 (bvdetect)

📌 维护:
  /总结状态 (bvstat)
  /总结清缓存 (bvclear)
  /总结模型 (bvmodel)

💡 例: /bv https://www.bilibili.com/video/BV1xx...
ℹ️ 总结默认以图片形式发送,可在配置中切换。
"""


async def handle_help(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    login_status = "✅ 已登录" if services.is_logged_in() else "❌ 未登录"
    platform_scope = "B站 / YouTube / 抖音 " if services.config.enable_multi_platform else "B站"
    yield event.plain_result(  # type: ignore[attr-defined]
        HELP_TEMPLATE.format(login_status=login_status, platform_scope=platform_scope)
    )
