"""Health-check (`/总结状态`) and cache-clear (`/总结清缓存`) handlers."""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator

from ..api.endpoints import clear_video_info_cache, video_info_cache_size
from ..api.wbi import clear_wbi_cache
from ..core.logging import get_logger
from ..llm.provider import DisabledLLMProvider
from ..services import BiliVideoServices

logger = get_logger("BiliVideo/Status")


async def handle_status(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    cfg = services.config
    cookie_state = "✅ 已登录" if services.is_logged_in() else "❌ 未登录"
    if not cfg.enable_auto_push:
        scheduler_state = "关闭(配置)"
    elif services.scheduler is not None and services.scheduler.is_running():
        scheduler_state = "✅ 运行中"
    else:
        scheduler_state = "⚠️ 已启用但未运行"
    targets = await services.subscription_manager.get_push_targets()
    backends = ", ".join(services.renderer.available_backends) or "无 (将回退纯文本)"
    diagnostics = getattr(services.renderer, "backend_diagnostics", {})
    render_diag_lines = "\n".join(
        f"  - {name}: {reason}" for name, reason in diagnostics.items()
    )
    if render_diag_lines:
        render_diag_lines = f"\n🔎 渲染诊断:\n{render_diag_lines}"
    wkhtml = "✅" if shutil.which("wkhtmltoimage") or shutil.which("wkhtmltoimage.exe") else "❌"
    if shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"):
        ffmpeg = "✅ 系统"
    else:
        try:
            import imageio_ffmpeg

            ffmpeg = "✅ 内建" if imageio_ffmpeg.get_ffmpeg_exe() else "❌"
        except Exception:
            ffmpeg = "❌"
    if isinstance(services.llm, DisabledLLMProvider):
        llm_state = "未配置"
    elif cfg.is_openai_compatible:
        llm_state = cfg.llm_model
    else:
        pinned = getattr(services.llm, "provider_id", "") or ""
        llm_state = f"astrbot:{pinned}" if pinned else "astrbot 当前模型"

    if cfg.enable_multi_platform:
        yt_cookies = "有" if services.youtube_cookies.has() else "无"
        multi_state = f"on (实验,仅 /总结;YT cookies:{yt_cookies})"
    else:
        multi_state = "off"

    body = (
        "🩺 biliVideo 状态\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📌 版本: 2.0.0\n"
        f"🔐 登录: {cookie_state}\n"
        f"🤖 LLM: {cfg.llm_provider} / {llm_state}\n"
        f"🎨 渲染后端: {backends}\n"
        f"🛠 系统工具: ffmpeg {ffmpeg}  wkhtmltoimage {wkhtml}\n"
        f"🔁 自动识别: {'开' if services.enable_miniapp_detect else '关'}\n"
        f"🌐 多平台: {multi_state}\n"
        f"📡 定时检查: {scheduler_state} (间隔 {cfg.check_interval_minutes} 分钟)\n"
        f"📋 推送目标: {len(targets)} 个\n"
        f"🗄  视频信息缓存: {video_info_cache_size()} 条\n"
        f"⏳ 用户冷却窗口: {cfg.user_cooldown_seconds} 秒\n"
        f"🖼 图片输出: {'on' if cfg.output_image else 'off'}  / "
        f" 自动分图: {'on' if cfg.enable_auto_split else 'off'}\n"
        f"💬 合并转发: {'on' if cfg.enable_forward_message else 'off'}\n"
        f"{render_diag_lines}\n"
    )
    yield event.plain_result(body)  # type: ignore[attr-defined]


async def handle_clear_cache(services: BiliVideoServices, event: object) -> AsyncIterator[object]:
    before = video_info_cache_size()
    await clear_video_info_cache()
    await clear_wbi_cache()
    await services.orchestrator.clear_cache()
    yield event.plain_result(  # type: ignore[attr-defined]
        f"🧹 已清除缓存(视频信息 {before} 条 + WBI 密钥 + 总结结果)"
    )
