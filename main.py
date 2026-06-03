"""biliVideo plugin entry point.

This file is intentionally thin: it only registers the AstrBot Star
class, builds the service container, and forwards every command to the
matching handler in `bilivideo.handlers`. All non-trivial logic lives
inside the `bilivideo` sub-package.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from .bilivideo import handlers
from .bilivideo.core.config import PluginConfig
from .bilivideo.core.logging import get_logger
from .bilivideo.handlers.scheduled_push import push_callback
from .bilivideo.services import BiliVideoServices
from .bilivideo.subscription.scheduler import CheckScheduler
from .bilivideo.tools import register_ai_tools


class BiliVideoPlugin(Star):
    """AstrBot plugin entry. Registers commands and delegates to handlers."""

    def __init__(self, context: Context, config: dict) -> None:
        super().__init__(context)

        plugin_config = PluginConfig.from_mapping(config or {})
        data_dir = str(StarTools.get_data_dir("astrbot_plugin_bilivideo"))

        self._tag = get_logger("BiliVideo", debug_enabled=plugin_config.debug_mode)
        self._tag.info(f"loading plugin (data_dir={data_dir})")

        self._services = BiliVideoServices(
            config=plugin_config,
            data_dir=data_dir,
            astrbot_context=context,
        )

        # Seed push targets from config (idempotent). Held as attribute so
        # ruff's "dangling task" check is satisfied and the task isn't
        # garbage-collected before it runs.
        self._seed_task = asyncio.create_task(self._seed_push_targets(plugin_config))

        # Wire scheduled push
        self._services.scheduler = CheckScheduler(
            self._services.subscription_manager,
            lambda origin, sub: push_callback(self._services, origin, sub),
            interval_seconds=plugin_config.check_interval_minutes * 60,
        )
        if plugin_config.enable_auto_push:
            self._services.scheduler.start()
            self._tag.info("scheduler started")
        else:
            self._tag.info("scheduler disabled")

        # AI function-call tools
        try:
            register_ai_tools(self._services, context)
        except Exception as exc:  # pragma: no cover - depends on AstrBot version
            self._tag.warning(f"AI tool registration failed: {exc}")

        login_state = "logged in" if self._services.is_logged_in() else "no SESSDATA"
        logger.info(f"BiliVideo plugin ready ({login_state})")

    async def _seed_push_targets(self, config: PluginConfig) -> None:
        try:
            for gid in config.push_groups:
                await self._services.subscription_manager.add_push_target(
                    f"{config.platform_prefix}:GroupMessage:{gid}", f"群{gid}"
                )
            for uid in config.push_users:
                await self._services.subscription_manager.add_push_target(
                    f"{config.platform_prefix}:FriendMessage:{uid}", f"QQ{uid}"
                )
        except Exception as exc:
            self._tag.warning(f"seed push targets failed: {exc}")

    # ──────────────────────── command bindings ────────────────────────

    @filter.command("总结帮助", alias={"bvhelp", "总结help"})
    async def cmd_help(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_help(self._services, event):
            yield resp

    @filter.command("识别开关", alias={"bvdetect", "detect_toggle", "切换识别"})
    async def cmd_toggle_detect(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_toggle_detect(self._services, event):
            yield resp

    @filter.command("总结状态", alias={"bvstat", "总结status", "插件状态"})
    async def cmd_status(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_status(self._services, event):
            yield resp

    @filter.command("总结清缓存", alias={"bvclear", "清缓存"})
    async def cmd_clear_cache(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_clear_cache(self._services, event):
            yield resp

    @filter.command("总结模型", alias={"bvmodel", "模型列表", "切换模型"})
    async def cmd_model(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_model(self._services, event):
            yield resp

    @filter.command("B站登录", alias={"bvlogin", "bili_login", "哔哩登录", "B站扫码登录", "扫码登录"})
    async def cmd_login(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_login(self._services, event):
            yield resp

    @filter.command("B站登出", alias={"bvlogout", "bili_logout", "哔哩登出"})
    async def cmd_logout(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_logout(self._services, event):
            yield resp

    @filter.command("YT登录", alias={"ytlogin", "yt登录", "油管登录", "youtube登录"})
    async def cmd_youtube_login(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_youtube_login(self._services, event):
            yield resp

    @filter.command("YT登出", alias={"ytlogout", "yt登出", "油管登出", "youtube登出"})
    async def cmd_youtube_logout(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_youtube_logout(self._services, event):
            yield resp

    @filter.command("总结", alias={"bv", "BiliVideo", "视频总结"})
    async def cmd_summary(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_summary(self._services, event):
            yield resp

    @filter.command("最新视频", alias={"latest"})
    async def cmd_latest_video(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_latest_video(self._services, event):
            yield resp

    @filter.command("订阅", alias={"sub", "subscribe", "关注UP"})
    async def cmd_subscribe(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_subscribe(self._services, event):
            yield resp

    @filter.command("取消订阅", alias={"unsub", "unsubscribe", "取关UP"})
    async def cmd_unsubscribe(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_unsubscribe(self._services, event):
            yield resp

    @filter.command("订阅列表", alias={"sublist", "subs", "订阅列表查看"})
    async def cmd_list_subs(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_list_subscriptions(self._services, event):
            yield resp

    @filter.command("检查更新", alias={"check", "手动检查"})
    async def cmd_check_updates(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_check_updates(self._services, event):
            yield resp

    @filter.command("添加推送群", alias={"addpg", "add_push_group"})
    async def cmd_add_push_group(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_add_push_group(self._services, event):
            yield resp

    @filter.command("添加推送号", alias={"addpu", "add_push_user"})
    async def cmd_add_push_user(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_add_push_user(self._services, event):
            yield resp

    @filter.command("推送列表", alias={"pushls", "push_list", "推送目标"})
    async def cmd_list_push(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_list_push(self._services, event):
            yield resp

    @filter.command("移除推送", alias={"rmpush", "remove_push", "删除推送"})
    async def cmd_remove_push(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_remove_push(self._services, event):
            yield resp

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        async for resp in handlers.handle_auto_detect(self._services, event):
            yield resp

    # ────────────────────── lifecycle ───────────────────────

    async def terminate(self) -> None:
        await self._services.shutdown()
        logger.info("BiliVideo plugin terminated")
