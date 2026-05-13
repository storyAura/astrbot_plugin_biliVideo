"""
BiliVideo 视频总结插件

订阅 B站 UP主，定时/手动生成 AI 视频总结并推送到聊天
"""

import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass, field

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.message_components import Plain, Image, Node, Nodes
from astrbot.api import logger

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult, ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext

from .services.subscription import SubscriptionManager
from .services.bilibili_api import get_up_info, get_latest_videos, search_up_by_name, get_video_info, resolve_short_url, search_videos, get_video_info
from .services.bilibili_login import BilibiliLogin
from .services.note_service import NoteService
from .services.search_service import SearchService
from .utils.url_parser import detect_platform, extract_bilibili_mid
from .utils.md_to_image import render_note_image, render_note_images


@dataclass
class BilibiliSearchListTool(FunctionTool[AstrAgentContext]):
    """
    B站视频搜索列表工具

    AI 调用此工具搜索B站视频，返回视频列表，不下载转写
    """
    name: str = "bilibili_search_list"
    description: str = (
        "搜索B站视频并返回视频列表（包含BV号）。"
        "仅返回搜索结果，不下载转写视频内容。"
        "如需下载转写视频内容，请将选中的BV号传给 bilibili_search_download 工具。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，如视频标题、UP主名、主题等",
                },
                "count": {
                    "type": "integer",
                    "description": "返回的视频数量，不指定则使用配置默认值",
                },
                "order": {
                    "type": "string",
                    "description": "排序方式：totalrank(综合排序)、click(播放量从高到低)、pubdate(最新发布)、dm(弹幕数)、stow(收藏数)。默认为 totalrank",
                },
                "duration": {
                    "type": "integer",
                    "description": "时长过滤：0(全部)、1(10分钟内)、2(10-30分钟)、3(30-60分钟)、4(60分钟以上)。默认为 0",
                },
            },
            "required": ["keyword"],
        }
    )
    plugin_instance: object = None

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        keyword = kwargs.get("keyword", "")
        default_count = self.plugin_instance.config.get("default_count", 20)
        count = int(kwargs.get("count", default_count))
        order = kwargs.get("order", "totalrank")
        duration = int(kwargs.get("duration", 0))

        if not keyword:
            return "错误：请提供搜索关键词"

        valid_orders = ["totalrank", "click", "pubdate", "dm", "stow"]
        if order not in valid_orders:
            order = "totalrank"

        if duration not in [0, 1, 2, 3, 4]:
            duration = 0

        try:
            search_result = await search_videos(
                keyword=keyword,
                page_size=count,
                order=order,
                duration=duration,
                cookies=self.plugin_instance.bili_cookies if self.plugin_instance else None,
            )

            if not search_result or not search_result.get("results"):
                return f"未找到与「{keyword}」相关的视频"

            videos = search_result["results"]
            total = search_result.get("numResults", len(videos))

            video_list = []
            for i, v in enumerate(videos, 1):
                video_list.append({
                    "index": i,
                    "bvid": v.get("bvid", ""),
                    "title": v.get("title", ""),
                    "author": v.get("author", ""),
                    "play": v.get("play", 0),
                    "duration": v.get("duration", ""),
                    "url": v.get("url", ""),
                })

            result = {
                "keyword": keyword,
                "total": total,
                "returned": len(videos),
                "videos": video_list,
            }

            return json.dumps(result, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"[BilibiliSearchListTool] 搜索失败: {e}", exc_info=True)
            return f"搜索失败: {str(e)}"


@dataclass
class BilibiliSearchDownloadTool(FunctionTool[AstrAgentContext]):
    """
    B站视频下载转写工具

    AI 调用此工具下载并转写指定的B站视频
    """
    name: str = "bilibili_search_download"
    description: str = ""
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "folder_name": {
                    "type": "string",
                    "description": "文件夹名称，用于标识这批转写内容",
                },
                "bv_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "BV号数组，支持一次传入多个BV号，如 ['BV1xxx', 'BV2yyy', 'BV3zzz']。不要多次调用，一次传入所有需要处理的BV号",
                },
            },
            "required": ["folder_name", "bv_list"],
        }
    )
    plugin_instance: object = None

    def __post_init__(self):
        default_download = self.plugin_instance.config.get("default_download_count", 3) if self.plugin_instance else 3
        object.__setattr__(self, 'description', (
            f"下载并转写视频内容。"
            f"先通过 bilibili_search_list 搜索获取BV号，再调用此工具下载转写视频内容。"
            f"bv_list 参数支持一次传入多个BV号，建议每次下载 {default_download} 个左右。"
            f"重要：调用一次即可，后台会自动处理所有视频，完成后会自动唤醒你继续处理，无需重复调用此工具。"
        ))

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        folder_name = kwargs.get("folder_name", "")
        bv_list = kwargs.get("bv_list", [])

        if not folder_name:
            return "错误：请提供文件夹名称"
        if not bv_list or not isinstance(bv_list, list):
            return "错误：请提供BV号列表"

        try:
            event = context.context.event
        except Exception as e:
            logger.warning(f"[BilibiliSearchDownloadTool] 获取上下文失败: {e}")
            return f"错误：获取会话上下文失败 - {e}"

        old_task = self.plugin_instance._current_download_task
        if old_task and not old_task.done():
            logger.info("[BilibiliSearchDownloadTool] 取消旧的下载任务")
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass

        new_task = asyncio.create_task(
            self._background_process(
                folder_name=folder_name,
                bv_list=bv_list,
                event=event,
            )
        )
        self.plugin_instance._current_download_task = new_task

        return f"已开始下载转写 {len(bv_list)} 个视频，完成后会自动通知你。"

    async def _background_process(
        self,
        folder_name: str,
        bv_list: list,
        event: AstrMessageEvent,
    ):
        """后台处理任务，完成后直接唤醒主对话"""
        try:
            from astrbot.core.cron.events import CronMessageEvent
            from astrbot.core.provider.entities import ProviderRequest

            # 兼容不同版本的 AstrBot 工具注册 API 和 agent 构建 API
            try:
                from astrbot.core.astr_main_agent import (
                    MainAgentBuildConfig,
                    _get_session_conv,
                    build_main_agent,
                )
            except (ImportError, ModuleNotFoundError):
                # 降级：不使用 agent 构建，直接发送完成消息
                build_main_agent = None
                MainAgentBuildConfig = None
                _get_session_conv = None

            try:
                from astrbot.core.tools.registry import get_builtin_tool_class
            except (ImportError, ModuleNotFoundError):
                try:
                    from astrbot.core.tools import get_builtin_tool_class
                except (ImportError, ModuleNotFoundError):
                    get_builtin_tool_class = lambda x: None

            search_service = self.plugin_instance.search_service
            max_concurrent = self.plugin_instance.config.get("search_max_concurrent", 1)
            quality = self.plugin_instance.config.get("download_quality", "fast")

            umo = event.unified_msg_origin
            progress_msg_sent = {"count": 0}
            
            # 检查是否显示进度
            show_progress = self.plugin_instance.config.get("search_show_progress", True)

            async def progress_callback(progress: dict):
                # 如果配置关闭了进度显示，只在最后一条时发送
                if not show_progress and not progress.get("is_last", False):
                    return
                
                try:
                    completed = progress.get("completed", 0)
                    total = progress.get("total", 0)
                    title = progress.get("title", "")
                    success = progress.get("success", True)
                    error = progress.get("error", "")
                    is_last = progress.get("is_last", False)
                    success_count = progress.get("success_count", 0)
                    failed_count = progress.get("failed_count", 0)

                    if success:
                        status_line = f"✅ 进度: {completed}/{total} - {title}"
                    else:
                        error_short = error[:30] + "..." if len(error) > 30 else error
                        status_line = f"❌ 进度: {completed}/{total} - {title}（{error_short}）"

                    if is_last:
                        msg = f"{status_line}\n📝 转写完成（成功{success_count}个，失败{failed_count}个），即将为您分析..."
                    else:
                        msg = status_line

                    chain = MessageChain().message(msg)
                    await self.plugin_instance.context.send_message(umo, chain)
                    progress_msg_sent["count"] += 1
                except Exception as e:
                    logger.warning(f"[BilibiliSearchDownloadTool] 进度回调失败: {e}")

            result = await search_service.process_by_bv_list(
                bv_list=bv_list,
                folder_name=folder_name,
                max_concurrent=max_concurrent,
                quality=quality,
                cookies=self.plugin_instance.bili_cookies,
                progress_callback=progress_callback,
                prefer_subtitle=self.plugin_instance.config.get("prefer_subtitle", True),
            )

            # 读取所有成功转写的内容
            all_transcripts = []
            video_info_list = []  # 存储视频信息用于合并转发
            for video in result.videos:
                if video.success and video.transcript_text:
                    all_transcripts.append({
                        "title": video.title,
                        "author": video.author,
                        "url": video.url,
                        "bvid": video.bvid,
                        "transcript": video.transcript_text,
                    })
                    
                    # 尝试获取视频详细信息（用于合并转发）
                    try:
                        video_info = await get_video_info(video.bvid, cookies=self.plugin_instance.bili_cookies)
                        if video_info:
                            video_info_list.append(video_info)
                    except Exception as e:
                        logger.warning(f"[BilibiliSearchDownloadTool] 获取视频 {video.bvid} 详细信息失败: {e}")

            # 直接生成总结并发送
            if all_transcripts:
                logger.info(f"[BilibiliSearchDownloadTool] 开始生成总结，共 {len(all_transcripts)} 个视频")

                # 构建总结提示词
                transcript_text = "\n\n".join([
                    f"【视频 {i+1}】{t['title']}\n{t['transcript']}"
                    for i, t in enumerate(all_transcripts)
                ])

                summary_prompt = (
                    "请为以下B站视频内容生成一份详细的结构化总结。\n\n"
                    "要求：\n"
                    "1. 使用 Markdown 格式\n"
                    "2. 包含：核心观点、关键要点、时间线（如有）、总结\n"
                    "3. 语言简洁清晰，突出重点\n"
                    "4. 如果是多个视频，分别总结并加上视频标题\n\n"
                    f"{transcript_text}"
                )

                # 调用 LLM 生成总结
                try:
                    note_text = await self.plugin_instance._ask_llm(summary_prompt)

                    # 渲染并发送（支持图片和文本模式）
                    render_result = self.plugin_instance._render_and_get_chain(note_text)

                    # 检查是否启用合并转发模式
                    if self.plugin_instance.config.get("enable_forward_message", False):
                        logger.info("[BilibiliSearchDownloadTool] 使用合并转发模式发送总结")
                        
                        # 如果是多个视频，为每个视频创建合并转发
                        if len(all_transcripts) > 1:
                            # 多视频：创建一个包含所有视频的合并转发
                            from astrbot.api.message_components import Node, Nodes, Plain, Image
                            import time as _time
                            
                            nodes = []
                            bot_name = "BiliVideo 助手"
                            bot_uin = "0"
                            
                            # 添加标题节点
                            nodes.append(Node(
                                content=[Plain(f"📝 搜索结果总结（共 {len(all_transcripts)} 个视频）")],
                                name=bot_name,
                                uin=bot_uin
                            ))
                            
                            # 为每个视频添加信息节点（包含封面和详细信息）
                            for i, t in enumerate(all_transcripts, 1):
                                video_content = []
                                
                                # 尝试添加封面图
                                if i <= len(video_info_list):
                                    video_info = video_info_list[i-1]
                                    pic_url = video_info.get("pic", "")
                                    if pic_url:
                                        if pic_url.startswith("//"):
                                            pic_url = "https:" + pic_url
                                        video_content.append(Image.fromURL(pic_url))
                                    
                                    # 使用详细信息
                                    video_info_text = f"📺 视频 {i}: {video_info.get('title', t['title'])}\n"
                                    video_info_text += f"👤 UP主: {video_info.get('owner_name', t['author'])}\n"
                                    
                                    # 添加播放数据
                                    def fmt_num(n):
                                        if isinstance(n, (int, float)) and n >= 10000:
                                            return f"{n / 10000:.1f}万"
                                        return str(n)
                                    
                                    video_info_text += (
                                        f"▶️ {fmt_num(video_info.get('view', 0))}播放  "
                                        f"💬 {fmt_num(video_info.get('danmaku', 0))}弹幕  "
                                        f"👍 {fmt_num(video_info.get('like', 0))}点赞\n"
                                    )
                                    video_info_text += f"🔗 {t['url']}"
                                else:
                                    # 回退到基本信息
                                    video_info_text = (
                                        f"📺 视频 {i}: {t['title']}\n"
                                        f"👤 UP主: {t['author']}\n"
                                        f"🔗 {t['url']}"
                                    )
                                
                                video_content.append(Plain(video_info_text))
                                nodes.append(Node(
                                    content=video_content,
                                    name=bot_name,
                                    uin=bot_uin
                                ))
                            
                            # 添加总结节点
                            if isinstance(render_result, list):
                                # 图片模式
                                for i, img in enumerate(render_result):
                                    label = (
                                        "📝 AI 综合总结"
                                        if i == 0
                                        else f"📝 AI 综合总结（第 {i + 1} 页）"
                                    )
                                    nodes.append(Node(
                                        content=[Plain(label), img],
                                        name=bot_name,
                                        uin=bot_uin
                                    ))
                            else:
                                # 文本模式
                                nodes.append(Node(
                                    content=[Plain(f"📝 AI 综合总结\n\n{render_result}")],
                                    name=bot_name,
                                    uin=bot_uin
                                ))
                            
                            forward_nodes = Nodes(nodes=nodes)
                            chain = MessageChain()
                            chain.chain.append(forward_nodes)
                            await self.plugin_instance.context.send_message(umo, chain)
                        else:
                            # 单视频：获取视频详细信息并使用标准合并转发
                            try:
                                video_info = await get_video_info(
                                    all_transcripts[0]['bvid'],
                                    cookies=self.plugin_instance.bili_cookies
                                )
                                if video_info:
                                    forward_nodes = self.plugin_instance._build_forward_nodes(
                                        video_info, render_result
                                    )
                                    chain = MessageChain()
                                    chain.chain.append(forward_nodes)
                                    await self.plugin_instance.context.send_message(umo, chain)
                                else:
                                    # 回退到普通模式
                                    if isinstance(render_result, list):
                                        for img_comp in render_result:
                                            chain = MessageChain()
                                            chain.chain.append(img_comp)
                                            await self.plugin_instance.context.send_message(umo, chain)
                                    else:
                                        chain = MessageChain().message(render_result)
                                        await self.plugin_instance.context.send_message(umo, chain)
                            except Exception as e:
                                logger.error(f"[BilibiliSearchDownloadTool] 获取视频信息失败: {e}")
                                # 回退到普通模式
                                if isinstance(render_result, list):
                                    for img_comp in render_result:
                                        chain = MessageChain()
                                        chain.chain.append(img_comp)
                                        await self.plugin_instance.context.send_message(umo, chain)
                                else:
                                    chain = MessageChain().message(render_result)
                                    await self.plugin_instance.context.send_message(umo, chain)
                    else:
                        # 普通模式
                        if isinstance(render_result, list):
                            # 图片模式
                            for img_comp in render_result:
                                chain = MessageChain()
                                chain.chain.append(img_comp)
                                await self.plugin_instance.context.send_message(umo, chain)
                        else:
                            # 文本模式
                            chain = MessageChain().message(render_result)
                            await self.plugin_instance.context.send_message(umo, chain)

                    logger.info("[BilibiliSearchDownloadTool] 总结已生成并发送")
                    return
                except Exception as e:
                    logger.error(f"[BilibiliSearchDownloadTool] 生成总结失败: {e}")
                    # 降级：发送完成消息

            # 降级：发送完成消息
            completion_msg = (
                f"📝 B站视频下载转写任务已完成\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📂 文件夹: {folder_name}\n"
                f"✅ 成功: {result.success_count} 个\n"
                f"❌ 失败: {result.failed_count} 个\n"
                f"📁 文件位置: {result.folder_path}"
            )
            chain = MessageChain().message(completion_msg)
            await self.plugin_instance.context.send_message(umo, chain)

            logger.info(f"[BilibiliSearchDownloadTool] 任务完成: {folder_name}")

        except asyncio.CancelledError:
            logger.info(f"[BilibiliSearchDownloadTool] 任务被取消: {folder_name}")
            raise
        except Exception as e:
            logger.error(f"[BilibiliSearchDownloadTool] 后台处理失败: {e}", exc_info=True)
            try:
                chain = MessageChain().message(f"视频转写任务处理出错: {str(e)}")
                await self.plugin_instance.context.send_message(event.unified_msg_origin, chain)
            except Exception:
                pass


class BiliVideoPlugin(Star):
    """BiliVideo 视频总结插件"""

    def __init__(self, context: Context, config: dict):
        super().__init__(context)

        # 数据目录（使用框架规范 API）
        self.data_dir = str(StarTools.get_data_dir("astrbot_plugin_bilivideo"))
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "images"), exist_ok=True)

        # 读取配置（由 AstrBot 直接传入）
        self.config = config

        # Debug 模式 —— 在其他所有初始化之前设置
        self._debug_mode = bool(self.config.get("debug_mode", False))
        if self._debug_mode:
            logger.info("═══════════ [BiliVideo] Debug 模式已启用 ═══════════")

        self._log("══════ [BiliVideo] 插件初始化开始 ══════")
        self._log(f"配置内容: { {k: v for k, v in self.config.items() if k not in ('cookies',)} }")

        # B站扫码登录服务
        self.bili_login = BilibiliLogin(self.data_dir)
        self.bili_cookies = self.bili_login.get_cookies()
        self._log(f"Cookie 状态: {'已加载, keys=' + str(list(self.bili_cookies.keys())) if self.bili_cookies else '无'}")

        # 解析群聊访问控制
        self.access_mode = self.config.get("access_mode", "blacklist")
        self.group_list = self._parse_list(
            str(self.config.get("group_list", ""))
        )
        self._log(f"访问控制: mode={self.access_mode}, group_list={self.group_list}")

        # 初始化服务
        self.subscription_mgr = SubscriptionManager(self.data_dir)
        self.note_service = NoteService(
            data_dir=self.data_dir,
            cookies=self.bili_cookies if self.bili_cookies else None,
        )
        self.search_service = SearchService(
            data_dir=self.data_dir,
            cookies=self.bili_cookies if self.bili_cookies else None,
        )

        # 从配置加载推送目标（与命令添加的合并，不重复）
        self._load_push_targets_from_config()

        # 定时任务
        self._check_task = None
        self._current_download_task = None  # 当前下载任务
        self._running = False

        # 启动定时检查
        if self.config.get("enable_auto_push", True):
            self._running = True
            self._check_task = asyncio.create_task(self._scheduled_check_loop())
            self._log("定时检查任务已启动")
        else:
            self._log("定时推送已禁用")

        # LLM Provider 配置
        self.llm_provider = self.config.get("llm_provider", "astrbot")
        self.llm_api_base = str(self.config.get("llm_api_base", "")).rstrip("/")
        self.llm_api_key = str(self.config.get("llm_api_key", ""))
        self.llm_model = str(self.config.get("llm_model", "gpt-4o-mini"))
        self._log(f"LLM Provider: {self.llm_provider}")

        # B站链接自动识别
        self.enable_miniapp_detect = bool(self.config.get("enable_miniapp_detect", False))
        self._log(f"B站链接自动识别: {'启用' if self.enable_miniapp_detect else '禁用'}")
        self._log("提示: 可用 /识别开关 命令实时切换")

        self._log("══════ [BiliVideo] 插件初始化完成 ══════")

        # 注册 AI 工具
        self._search_list_tool = BilibiliSearchListTool(plugin_instance=self)
        self._search_download_tool = BilibiliSearchDownloadTool(plugin_instance=self)
        self.context.add_llm_tools(self._search_list_tool)
        self.context.add_llm_tools(self._search_download_tool)
        self._log("已注册 bilibili_search_list 和 bilibili_search_download 工具供 AI 调用")

        if self.bili_login.is_logged_in():
            logger.info("BiliVideo 插件已加载（B站已登录）")
        else:
            logger.info("BiliVideo 插件已加载（B站未登录，请发送 /B站登录 扫码）")

    # ==================== 工具方法 ====================

    def _log(self, msg: str):
        """Debug 日志输出 —— 使用 logger.info 确保始终可见"""
        if self._debug_mode:
            logger.info(f"[BiliVideo/DBG] {msg}")

    def _load_push_targets_from_config(self):
        """从配置文件加载推送目标到 SubscriptionManager"""
        prefix = self.config.get("platform_prefix", "aiocqhttp")
        push_groups = str(self.config.get("push_groups", "")).strip()
        push_users = str(self.config.get("push_users", "")).strip()

        if push_groups:
            for gid in push_groups.split(","):
                gid = gid.strip()
                if gid and gid.isdigit():
                    origin = f"{prefix}:GroupMessage:{gid}"
                    self.subscription_mgr.add_push_target(origin, f"群{gid}")

        if push_users:
            for uid in push_users.split(","):
                uid = uid.strip()
                if uid and uid.isdigit():
                    origin = f"{prefix}:FriendMessage:{uid}"
                    self.subscription_mgr.add_push_target(origin, f"QQ{uid}")

    @staticmethod
    def _parse_list(text: str) -> set:
        """解析逗号分隔的列表为 set"""
        if not text or not text.strip():
            return set()
        return {item.strip() for item in text.split(',') if item.strip()}

    def _check_access(self, event: AstrMessageEvent) -> bool:
        """检查群是否有权使用插件（仅群维度，不看个人）"""
        try:
            origin = getattr(event, 'unified_msg_origin', '') or ''
            self._log(f"[AccessCheck] mode={self.access_mode}, origin={origin}, group_list={self.group_list}")

            if self.access_mode == 'all':
                self._log("[AccessCheck] 模式=all, 放行")
                return True

            if not self.group_list:
                self._log("[AccessCheck] group_list 为空, 放行")
                return True

            if self.access_mode == 'whitelist':
                for gid in self.group_list:
                    if f':{gid}' in origin or origin.endswith(gid):
                        self._log(f"[AccessCheck] 白名单命中: {gid}")
                        return True
                self._log("[AccessCheck] 白名单未命中, 拒绝")
                return False

            elif self.access_mode == 'blacklist':
                for gid in self.group_list:
                    if f':{gid}' in origin or origin.endswith(gid):
                        self._log(f"[AccessCheck] 黑名单命中: {gid}, 拒绝")
                        return False
                self._log("[AccessCheck] 黑名单未命中, 放行")
                return True

        except Exception as e:
            logger.warning(f"访问控制检查异常: {e}")

        return True

    @staticmethod
    def _parse_args(message_str) -> str:
        """从完整消息中提取命令后的参数"""
        if not message_str:
            return ""
        parts = str(message_str).strip().split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    def _render_and_get_chain(self, note_text: str):
        """
        将总结渲染为图片并返回消息链组件，或回退到纯文本。
        支持长内容自动拆分为多张图片。

        :return: list[Image] (图片模式) 或 str (文本模式)
        """
        if not self.config.get("output_image", True):
            self._log("[Render] output_image=False, 使用纯文本")
            return note_text

        import time
        base_filename = f"note_{int(time.time() * 1000)}"
        img_dir = os.path.join(self.data_dir, "images")

        # 检测是否需要分页（按 h2 章节数量）
        chapter_count = note_text.count('\n## ')
        enable_auto_split = self.config.get("enable_auto_split", True)
        max_cards = self.config.get("max_cards_per_image", 6)

        self._log(f"[Render] 检测到 {chapter_count} 个章节, 单图限制 {max_cards} 个")

        if enable_auto_split and chapter_count > max_cards:
            # 使用多图渲染
            self._log(f"[Render] 启用多图渲染模式")
            image_paths = render_note_images(
                note_text,
                output_dir=img_dir,
                base_filename=base_filename,
                max_cards_per_image=max_cards,
            )

            if image_paths:
                self._log(f"[Render] 多图渲染成功: {len(image_paths)} 张")
                return [Image.fromFileSystem(p) for p in image_paths]
            else:
                self._log("[Render] 多图渲染失败, 尝试单图渲染")

        # 单张图片模式（原有逻辑）
        img_path = os.path.join(img_dir, f"{base_filename}.png")
        self._log(f"[Render] 开始渲染单张图片: {img_path}")
        result = render_note_image(note_text, img_path)

        if result and os.path.exists(result):
            self._log(f"[Render] 图片渲染成功: {os.path.getsize(result)} bytes")
            return [Image.fromFileSystem(result)]
        else:
            self._log("[Render] 图片渲染失败, 回退到纯文本")
            return note_text

    def _build_forward_nodes(
        self,
        video_info: dict,
        note_result,
        bot_name: str = "BiliVideo 助手",
        bot_uin: str = "0",
    ) -> Nodes:
        """
        构建合并转发消息节点，将视频信息和 AI 总结打包在一起。

        :param video_info: get_video_info() 返回的视频信息字典
        :param note_result: _render_and_get_chain() 的返回值 (list[Image] 或 str)
        :param bot_name: 转发消息中显示的发送者名称
        :param bot_uin: 转发消息中显示的发送者 QQ 号
        :return: Nodes 对象
        """
        import time as _time

        nodes: list[Node] = []

        # ── Node 1: 视频封面 + 标题 ──
        cover_content: list = []
        pic_url = video_info.get("pic", "")
        if pic_url:
            if pic_url.startswith("//"):
                pic_url = "https:" + pic_url
            cover_content.append(Image.fromURL(pic_url))
        cover_content.append(Plain(f"📺 {video_info.get('title', '未知视频')}"))
        nodes.append(Node(content=cover_content, name=bot_name, uin=bot_uin))

        # ── Node 2: 视频详细信息 ──
        def _fmt_num(n) -> str:
            if isinstance(n, (int, float)) and n >= 10000:
                return f"{n / 10000:.1f}万"
            return str(n)

        info_lines: list[str] = []
        info_lines.append(f"👤 UP主: {video_info.get('owner_name', '未知')}")

        desc = video_info.get("desc", "")
        if desc:
            if len(desc) > 150:
                desc = desc[:150] + "..."
            info_lines.append(f"📝 简介: {desc}")

        pubdate = video_info.get("pubdate")
        if pubdate:
            try:
                pub_str = _time.strftime(
                    "%Y-%m-%d %H:%M", _time.localtime(pubdate)
                )
                info_lines.append(f"📅 发布时间: {pub_str}")
            except Exception:
                pass

        info_lines.append(
            f"▶️ {_fmt_num(video_info.get('view', 0))}播放  "
            f"💬 {_fmt_num(video_info.get('danmaku', 0))}弹幕  "
            f"👍 {_fmt_num(video_info.get('like', 0))}点赞"
        )

        bvid = video_info.get("bvid", "")
        if bvid:
            info_lines.append(f"🔗 https://www.bilibili.com/video/{bvid}")

        nodes.append(
            Node(
                content=[Plain("\n".join(info_lines))],
                name=bot_name,
                uin=bot_uin,
            )
        )

        # ── Node 3+: AI 总结 ──
        if isinstance(note_result, list):
            # 图片模式：每张图片单独一个 Node
            for i, img in enumerate(note_result):
                label = (
                    "📝 AI 视频总结"
                    if i == 0
                    else f"📝 AI 视频总结（第 {i + 1} 页）"
                )
                nodes.append(
                    Node(content=[Plain(label), img], name=bot_name, uin=bot_uin)
                )
        elif isinstance(note_result, str):
            # 文本模式：长文本分段，每段一个 Node
            max_chunk = 2000
            if len(note_result) <= max_chunk:
                nodes.append(
                    Node(
                        content=[Plain(f"📝 AI 视频总结\n\n{note_result}")],
                        name=bot_name,
                        uin=bot_uin,
                    )
                )
            else:
                chunks: list[str] = []
                remaining = note_result
                while remaining:
                    if len(remaining) <= max_chunk:
                        chunks.append(remaining)
                        break
                    cut = remaining.rfind("\n\n", 0, max_chunk)
                    if cut < int(max_chunk * 0.5):
                        cut = remaining.rfind("\n", 0, max_chunk)
                    if cut < int(max_chunk * 0.3):
                        cut = max_chunk
                    chunks.append(remaining[:cut])
                    remaining = remaining[cut:].lstrip("\n")

                for i, chunk in enumerate(chunks):
                    label = (
                        "📝 AI 视频总结"
                        if i == 0
                        else f"📝 AI 视频总结（第 {i + 1} 部分）"
                    )
                    nodes.append(
                        Node(
                            content=[Plain(f"{label}\n\n{chunk}")],
                            name=bot_name,
                            uin=bot_uin,
                        )
                    )

        self._log(f"[Forward] 构建合并转发: {len(nodes)} 个节点")
        return Nodes(nodes=nodes)

    # ==================== B站链接自动识别 ====================

    @filter.command("识别开关", alias={"detect_toggle", "切换识别"})
    async def toggle_detect_cmd(self, event: AstrMessageEvent):
        """实时切换B站链接自动识别开关"""
        self.enable_miniapp_detect = not self.enable_miniapp_detect
        # 同步到 config 字典（重载插件时保持一致）
        self.config["enable_miniapp_detect"] = self.enable_miniapp_detect
        try:
            if hasattr(self.config, 'save_config'):
                self.config.save_config()
        except Exception:
            pass
        status = "✅ 已开启" if self.enable_miniapp_detect else "❌ 已关闭"
        yield event.plain_result(f"B站链接自动识别: {status}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """自动识别消息中的B站视频链接并推送视频信息"""
        if not self.enable_miniapp_detect:
            return

        # 跳过命令消息
        raw_msg = event.message_str or ""
        if raw_msg.strip().startswith("/"):
            return

        # 检测是否是引用/回复消息（第一个组件是 reply 类型）
        is_reply_message = False
        has_at_component = False
        user_actual_content = ""  # 用户实际发送的内容（排除引用部分）
        
        try:
            if hasattr(event, 'message_obj') and event.message_obj:
                comps = event.message_obj.message or []
                if comps:
                    first_comp = comps[0]
                    comp_type = getattr(first_comp, 'type', None)
                    # OneBot 协议中 reply 类型表示这是引用/回复消息
                    if comp_type == 'reply':
                        is_reply_message = True
                        self._log(f"[AutoDetect] 检测到引用消息")
                    
                    # 提取用户实际发送的内容（跳过 reply 组件）
                    user_content_parts = []
                    for i, comp in enumerate(comps):
                        comp_type = getattr(comp, 'type', None)
                        
                        # 跳过 reply 组件（引用的内容）
                        if comp_type == 'reply':
                            continue
                        
                        # 检测艾特组件
                        if comp_type == 'at':
                            has_at_component = True
                            # 艾特也算用户内容的一部分
                            user_content_parts.append(f"@{getattr(comp, 'data', {}).get('qq', 'someone')}")
                        
                        # 提取文本内容
                        elif comp_type == 'text' or hasattr(comp, 'text'):
                            text = getattr(comp, 'text', str(comp))
                            user_content_parts.append(text)
                        
                        # 其他类型组件（图片、JSON等）
                        elif comp_type in ['image', 'json', 'face']:
                            # JSON 组件可能包含小程序链接，保留
                            user_content_parts.append(str(comp))
                    
                    user_actual_content = " ".join(user_content_parts).strip()
                    self._log(f"[AutoDetect] 用户实际内容: '{user_actual_content}'")
        except Exception as e:
            self._log(f"[AutoDetect] 解析消息组件异常: {e}")
            user_actual_content = raw_msg

        # 如果是引用消息，只检查用户实际发送的内容，不检查引用的内容
        if is_reply_message:
            self._log(f"[AutoDetect] 这是引用消息，只检查用户实际内容")
            
            # 定义触发关键词列表（用户明确表达想要查看/总结视频的意图）
            trigger_keywords = [
                '总结', '看看', '看一下', '看下', '分析', '讲的啥', '讲什么', '说的啥', '说什么',
                '内容', '视频', '这个', '这视频', '帮我看', '帮忙看', '解析', '翻译',
                'summary', 'summarize', 'analyze', 'video', 'watch', 'check', 'see',
                'bilibili', 'b23.tv', 'bv', 'www.bilibili.com', '哔哩哔哩'
            ]
            
            # 检查用户实际内容中是否包含 B站链接
            has_bili_in_user_content = any(keyword in user_actual_content.lower() for keyword in [
                'bilibili', 'b23.tv', 'bv', 'www.bilibili.com', '哔哩哔哩'
            ])
            has_bv_in_user_content = bool(re.search(r'BV[0-9A-Za-z]{10}', user_actual_content))
            has_url_in_user_content = bool(re.search(r'https?://.*bilibili', user_actual_content))
            
            # 检查是否包含触发关键词
            has_trigger_keyword = any(keyword in user_actual_content.lower() for keyword in trigger_keywords)
            
            # 如果用户实际内容中没有B站链接，且没有触发关键词，跳过识别
            if not has_bili_in_user_content and not has_bv_in_user_content and not has_url_in_user_content:
                if not has_trigger_keyword:
                    self._log(f"[AutoDetect] 引用消息中用户实际内容无B站链接且无触发关键词，跳过识别")
                    return
                else:
                    self._log(f"[AutoDetect] 引用消息中检测到触发关键词: '{user_actual_content}'，尝试从引用内容提取链接")
                    # 继续执行，从引用的消息中提取链接
            
            # 如果用户实际内容很短（<30字符）且没有明确的链接，检查是否有触发关键词
            if len(user_actual_content) < 30 and not has_url_in_user_content and not has_bv_in_user_content:
                if not has_trigger_keyword:
                    self._log(f"[AutoDetect] 引用消息中用户内容过短且无明确链接和触发关键词，跳过识别")
                    return
                else:
                    self._log(f"[AutoDetect] 引用消息中检测到触发关键词，继续处理")

        # 跳过纯艾特消息（包含 @ 但没有 B站链接特征）
        msg_stripped = user_actual_content if is_reply_message else raw_msg.strip()
        has_bili_keywords = any(keyword in msg_stripped.lower() for keyword in [
            'bilibili', 'b23.tv', 'bv', 'www.bilibili.com', '哔哩哔哩'
        ])
        
        # 如果消息以 @ 开头，且很短（<20字符），且没有B站关键词，则跳过
        if msg_stripped.startswith('@') and len(msg_stripped) < 20 and not has_bili_keywords:
            self._log(f"[AutoDetect] 跳过纯艾特消息: '{msg_stripped}'")
            return
        
        # 如果检测到艾特组件，且消息中没有B站链接特征，则跳过
        if has_at_component and not has_bili_keywords:
            # 进一步检查是否真的包含 BV 号或链接
            has_bv = bool(re.search(r'BV[0-9A-Za-z]{10}', msg_stripped))
            has_url = bool(re.search(r'https?://', msg_stripped))
            if not has_bv and not has_url:
                self._log(f"[AutoDetect] 跳过艾特消息（无B站链接）: '{msg_stripped}'")
                return

        # 访问控制
        if not self._check_access(event):
            return

        bili_url = ""
        bvid = None
        
        # 判断是否需要从引用内容中提取链接
        # 如果是引用消息且用户内容中有触发关键词，则允许从完整消息提取
        allow_extract_from_reply = False
        if is_reply_message:
            # 检查用户内容中是否有触发关键词
            trigger_keywords = [
                '总结', '看看', '看一下', '看下', '分析', '讲的啥', '讲什么', '说的啥', '说什么',
                '内容', '视频', '这个', '这视频', '帮我看', '帮忙看', '解析', '翻译',
                'summary', 'summarize', 'analyze', 'video', 'watch', 'check', 'see'
            ]
            has_trigger = any(keyword in user_actual_content.lower() for keyword in trigger_keywords)
            # 如果用户内容中没有直接的B站链接，但有触发关键词，则允许从引用提取
            has_direct_link = any(keyword in user_actual_content.lower() for keyword in [
                'bilibili', 'b23.tv', 'bv', 'www.bilibili.com'
            ]) or bool(re.search(r'BV[0-9A-Za-z]{10}', user_actual_content))
            
            if has_trigger and not has_direct_link:
                allow_extract_from_reply = True
                self._log(f"[AutoDetect] 引用消息中检测到触发关键词且无直接链接，允许从引用内容提取")

        # ---- 1. 尝试从 raw_message 提取 QQ 小程序 / JSON 卡片 ----
        # 如果是引用消息且不允许从引用提取，则跳过 JSON 卡片提取
        if not is_reply_message or allow_extract_from_reply:
            try:
                if hasattr(event, 'message_obj') and event.message_obj:
                    raw = getattr(event.message_obj, 'raw_message', None)
                    logger.info(f"[AutoDetect] raw_message type={type(raw).__name__}, truthy={bool(raw)}")
                    if raw:
                        bili_url = self._extract_bili_url_from_raw(raw)

                    # 遍历消息组件的 raw / data 属性（跳过第一个回复/引用组件）
                    comps = event.message_obj.message or []
                    self._log(f"[AutoDetect] 小程序检测: 组件数量={len(comps)}")
                    for i, comp in enumerate(comps):
                        # 跳过第一个组件（可能是回复/引用）
                        if i == 0:
                            comp_type = getattr(comp, 'type', None)
                            comp_str = str(comp)
                            if comp_type == 'reply' or (comp_type == 'json' and 'appid' in comp_str):
                                self._log(f"[AutoDetect] 跳过第一个组件（可能是回复/引用）: type={comp_type}")
                                continue
                        comp_raw = getattr(comp, 'raw', None) or getattr(comp, 'data', None)
                        if comp_raw:
                            bili_url = self._extract_bili_url_from_raw(comp_raw)
                            if bili_url:
                                break

                    # 兜底：尝试将每个组件转为字符串后解析 JSON（跳过第一个回复/引用组件）
                    if not bili_url and event.message_obj.message:
                        for i, comp in enumerate(comps):
                            # 跳过第一个组件（可能是回复/引用）
                            if i == 0:
                                comp_type = getattr(comp, 'type', None)
                                comp_str = str(comp)
                                if comp_type == 'reply' or (comp_type == 'json' and 'appid' in comp_str):
                                    continue
                            comp_str = str(comp)
                            if 'bilibili' in comp_str.lower() or 'b23.tv' in comp_str.lower():
                                logger.info(f"[AutoDetect] 尝试 str(comp) 解析, len={len(comp_str)}")
                                # 尝试直接 JSON 解析
                                bili_url = self._try_parse_json_for_url(comp_str)
                                if bili_url:
                                    break
                                # 尝试从字符串中直接用正则匹配 URL
                                url_match = re.search(r'https?://[^\s\"\'\}\]]+bilibili\.com/video/(BV[0-9A-Za-z]{10})', comp_str)
                                if url_match:
                                    bvid = url_match.group(1)
                                    logger.info(f"[AutoDetect] 从 str(comp) 正则匹配到 BV: {bvid}")
                                    break
                                url_match = re.search(r'https?://b23\.tv/\S+', comp_str)
                                if url_match:
                                    bili_url = url_match.group(0).rstrip('"}\']')
                                    logger.info(f"[AutoDetect] 从 str(comp) 匹配到短链: {bili_url}")
                                    break
                                # qqdocurl 可能直接在字符串中
                                qqdoc_match = re.search(r'"qqdocurl"\s*:\s*"(https?://[^"]+)"', comp_str)
                                if qqdoc_match:
                                    bili_url = qqdoc_match.group(1)
                                    logger.info(f"[AutoDetect] 从 str(comp) 匹配到 qqdocurl: {bili_url}")
                                    break
            except Exception as e:
                logger.error(f"[AutoDetect] 解析消息异常: {e}", exc_info=True)

            # ---- 2. message_str 可能本身就是 JSON ----
            if not bili_url and not bvid and raw_msg.strip().startswith("{"):
                bili_url = self._try_parse_json_for_url(raw_msg.strip())
        else:
            self._log(f"[AutoDetect] 引用消息且无触发关键词，跳过 JSON 卡片提取")

        logger.info(f"[AutoDetect] 提取结果: bili_url={bili_url!r}, bvid={bvid}")

        # ---- 3. 如果从 JSON 拿到了 URL，提取 BV 号 ----
        if bili_url:
            self._log(f"[AutoDetect] 从 JSON 卡片提取到 URL: {bili_url}")
            bv_match = re.search(r'(BV[0-9A-Za-z]{10})', bili_url)
            if bv_match:
                bvid = bv_match.group(1)
            elif 'b23.tv' in bili_url or 'bili' in bili_url:
                resolved = await resolve_short_url(bili_url)
                if resolved:
                    self._log(f"[AutoDetect] 短链解析结果: {resolved}")
                    bv_match = re.search(r'(BV[0-9A-Za-z]{10})', resolved)
                    if bv_match:
                        bvid = bv_match.group(1)

        # ---- 4. 从纯文本中提取 ----
        # 如果是引用消息且允许从引用提取，使用完整消息；否则只用用户实际内容
        if not bvid:
            if is_reply_message and allow_extract_from_reply:
                # 允许从引用内容提取，使用完整消息
                all_text = raw_msg
                self._log(f"[AutoDetect] 引用消息且有触发关键词，从完整消息提取: '{all_text}'")
            elif is_reply_message:
                # 不允许从引用提取，只用用户实际内容
                all_text = user_actual_content
                self._log(f"[AutoDetect] 引用消息，只从用户实际内容提取: '{all_text}'")
            else:
                # 非引用消息，使用完整消息
                all_text = raw_msg
            
            try:
                if hasattr(event, 'message_obj') and event.message_obj and not is_reply_message:
                    parts = []
                    comps = event.message_obj.message or []
                    self._log(f"[AutoDetect] 消息组件数量: {len(comps)}")
                    # 跳过第一个 reply 组件
                    for i, comp in enumerate(comps):
                        # 检测是否是回复/引用组件
                        comp_type = getattr(comp, 'type', None)
                        comp_str = str(comp)
                        # OneBot 的回复类型是 'reply'，QQ小程序也可能是 'json' 且包含引用
                        if comp_type == 'reply' or (comp_type == 'json' and 'appid' in comp_str and i == 0):
                            self._log(f"[AutoDetect] 跳过回复/引用组件 [{i}]: type={comp_type}")
                            continue
                        if hasattr(comp, 'text'):
                            parts.append(comp.text)
                        elif isinstance(comp, str):
                            parts.append(comp)
                    if parts:
                        all_text = " ".join(parts)
                        self._log(f"[AutoDetect] 过滤后的文本: {all_text}")
            except Exception:
                pass

            # BV 号
            bv_match = re.search(r'(BV[0-9A-Za-z]{10})', all_text)
            if bv_match:
                bvid = bv_match.group(1)

            # bilibili.com 长链
            if not bvid:
                url_match = re.search(r'https?://(?:www\.)?bilibili\.com/video/(BV[0-9A-Za-z]{10})', all_text)
                if url_match:
                    bvid = url_match.group(1)

            # b23.tv 短链 (异步解析)
            if not bvid:
                short_match = re.search(r'https?://b23\.tv/\S+', all_text)
                if short_match:
                    resolved = await resolve_short_url(short_match.group(0))
                    if resolved:
                        bv_match = re.search(r'(BV[0-9A-Za-z]{10})', resolved)
                        if bv_match:
                            bvid = bv_match.group(1)

        if not bvid:
            return  # 没有检测到B站链接，静默放过

        self._log(f"[AutoDetect] 检测到 BV 号: {bvid}")

        # 获取视频信息并推送
        try:
            info = await get_video_info(bvid, cookies=self.bili_cookies)
            if not info:
                self._log(f"[AutoDetect] 获取视频信息失败: {bvid}")
                return

            def fmt_num(n):
                if n >= 10000:
                    return f"{n / 10000:.1f}万"
                return str(n)

            # 按配置构造文本（每次从 config 动态读取）
            video_url = f"https://www.bilibili.com/video/{bvid}"
            lines = []
            lines.append(f"📺 {info['title']}")

            if self.config.get("detect_show_uploader", True):
                lines.append(f"👤 UP主: {info['owner_name']}")

            if self.config.get("detect_show_desc", True) and info.get('desc'):
                desc = info['desc']
                if len(desc) > 100:
                    desc = desc[:100] + "..."
                lines.append(f"📝 简介: {desc}")

            if self.config.get("detect_show_pubtime", True) and info.get('pubdate'):
                import time as _time
                try:
                    pub_str = _time.strftime('%Y-%m-%d %H:%M', _time.localtime(info['pubdate']))
                    lines.append(f"📅 发布: {pub_str}")
                except Exception:
                    pass

            if self.config.get("detect_show_stats", True):
                lines.append(
                    f"▶️ {fmt_num(info['view'])}播放  "
                    f"💬 {fmt_num(info['danmaku'])}弹幕  "
                    f"👍 {fmt_num(info['like'])}点赞"
                )

            if self.config.get("detect_show_link", True):
                lines.append(f"🔗 {video_url}")

            text = "\n".join(lines)

            # 构建消息链
            chain = []
            if self.config.get("detect_show_cover", True):
                pic_url = info.get("pic", "")
                if pic_url:
                    if pic_url.startswith("//"):
                        pic_url = "https:" + pic_url
                    chain.append(Image.fromURL(pic_url))
            chain.append(Plain(text))

            yield event.chain_result(chain)

            # 自动总结
            if self.config.get("detect_auto_summary", False):
                self._log(f"[AutoDetect] 开始自动总结: {video_url}")
                yield event.plain_result("⏳ 正在生成视频总结...")
                try:
                    note = await self._generate_note(video_url)
                    result = self._render_and_get_chain(note)

                    # 合并转发模式
                    if self.config.get("enable_forward_message", False) and info:
                        self._log("[AutoDetect] 使用合并转发模式发送总结")
                        forward_nodes = self._build_forward_nodes(info, result)
                        yield event.chain_result([forward_nodes])
                    elif isinstance(result, list):
                        yield event.chain_result(result)
                    else:
                        yield event.plain_result(result)
                except Exception as se:
                    self._log(f"[AutoDetect] 自动总结失败: {se}")
                    yield event.plain_result(f"❌ 自动总结失败: {se}")

        except Exception as e:
            self._log(f"[AutoDetect] 处理异常: {e}")
            logger.error(f"B站链接自动识别处理异常: {e}", exc_info=True)

    # ---- 小程序 URL 提取辅助方法 ----

    def _extract_bili_url_from_raw(self, raw) -> str:
        """从 raw_message 中提取 B站 URL，支持 dict/list/str 格式"""
        if raw is None:
            return ""

        # raw 是 dict（已解析的 JSON 或 OneBot 消息段）
        if isinstance(raw, dict):
            url = self._find_bili_qqdocurl(raw)
            if url:
                return url
            # OneBot 消息段: {"type":"json","data":{"data":"{...}"}}
            if raw.get("type") == "json":
                inner = raw.get("data", {})
                if isinstance(inner, dict):
                    json_str = inner.get("data", "")
                    if isinstance(json_str, str):
                        return self._try_parse_json_for_url(json_str)
                elif isinstance(inner, str):
                    return self._try_parse_json_for_url(inner)

        # raw 是 list（OneBot 消息段列表）
        if isinstance(raw, list):
            for seg in raw:
                if not isinstance(seg, dict):
                    continue
                if seg.get("type") == "json":
                    inner = seg.get("data", {})
                    if isinstance(inner, dict):
                        json_str = inner.get("data", "")
                        if isinstance(json_str, str):
                            url = self._try_parse_json_for_url(json_str)
                            if url:
                                return url
                    elif isinstance(inner, str):
                        url = self._try_parse_json_for_url(inner)
                        if url:
                            return url

        # raw 是 str
        if isinstance(raw, str):
            raw_str = raw.strip()
            # 纯 JSON 字符串
            if raw_str.startswith("{"):
                url = self._try_parse_json_for_url(raw_str)
                if url:
                    return url
            # CQ 码: [CQ:json,data=...]
            cq_match = re.search(r'\[CQ:json,data=(.*?)\]', raw_str, re.S)
            if cq_match:
                cq_data = cq_match.group(1)
                cq_data = (
                    cq_data
                    .replace("&amp;", "&")
                    .replace("&#44;", ",")
                    .replace("&#91;", "[")
                    .replace("&#93;", "]")
                )
                url = self._try_parse_json_for_url(cq_data)
                if url:
                    return url

        return ""

    def _try_parse_json_for_url(self, text: str) -> str:
        """尝试从 JSON 字符串中提取 B站 URL"""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return self._find_bili_qqdocurl(data)
        except (json.JSONDecodeError, TypeError):
            pass
        return ""

    def _find_bili_qqdocurl(self, data: dict) -> str:
        """从已解析的 JSON dict 中查找 B站相关的 URL"""
        meta = data.get("meta")
        if not isinstance(meta, dict):
            return ""
        for _key, val in meta.items():
            if isinstance(val, dict):
                url = val.get("qqdocurl", "") or val.get("jumpUrl", "") or val.get("url", "")
                if url and self._is_bili_domain(url):
                    return url
        return ""

    @staticmethod
    def _is_bili_domain(url: str) -> bool:
        """检查 URL 是否属于 B站 相关域名"""
        import urllib.parse
        try:
            host = urllib.parse.urlparse(url).hostname or ""
            host = host.lower().rstrip(".")
            bili_domains = ("bilibili.com", "b23.tv", "bili2233.cn", "bili22.cn", "bili23.cn", "bili33.cn")
            return any(host == d or host.endswith("." + d) for d in bili_domains)
        except Exception:
            return False

    # ==================== 命令处理 ====================

    @filter.command("总结帮助", alias={"BiliVideo help", "总结help", "总结帮助"})
    async def show_help(self, event: AstrMessageEvent):
        """显示插件帮助信息"""
        login_status = "✅ 已登录" if self.bili_login.is_logged_in() else "❌ 未登录"
        help_text = (
            "📝 biliVideo 视频总结助手 v1.0.0\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"🔐 B站登录状态: {login_status}\n"
            "\n"
            "📌 登录命令:\n"
            "  /B站登录 → 扫码登录B站\n"
            "  /B站登出 → 退出B站登录\n"
            "\n"
            "📌 基本命令:\n"
            "  /总结 <B站视频链接或BV号>\n"
            "    → 为指定视频生成AI总结\n"
            "  /最新视频 <UP主UID、空间链接或昵称>\n"
            "    → 获取UP主最新视频并生成总结\n"
            "\n"
            "📌 订阅管理:\n"
            "  /订阅 <UP主UID、空间链接或昵称>\n"
            "    → 订阅UP主，有新视频自动推送总结\n"
            "  /取消订阅 <UP主UID、空间链接或昵称>\n"
            "    → 取消订阅\n"
            "  /订阅列表\n"
            "    → 查看当前订阅的UP主\n"
            "  /检查更新\n"
            "    → 手动检查订阅UP主的新视频\n"
            "\n"
            "📌 推送目标:\n"
            "  /添加推送群 <群号>\n"
            "    → 将QQ群加入推送列表\n"
            "  /添加推送号 <QQ号>\n"
            "    → 将QQ号加入推送列表\n"
            "  /推送列表\n"
            "    → 查看当前推送目标\n"
            "  /移除推送 <群号或QQ号>\n"
            "    → 移除推送目标\n"
            "\n"
            "💡 示例:\n"
            "  /总结 https://www.bilibili.com/video/BV1xx...\n"
            "  /总结 BV1xx411c7mD\n"
            "  /订阅 123456789\n"
            "  /添加推送群 123456789\n"
            "\n"
            "ℹ️ 总结默认以图片形式发送，可在配置中切换\n"
        )
        yield event.plain_result(help_text)

    @filter.command("B站登录", alias={"bili_login", "哔哩登录", "B站扫码登录", "扫码登录"})
    async def bili_login_cmd(self, event: AstrMessageEvent):
        """B站扫码登录"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return

        if self.bili_login.is_logged_in():
            yield event.plain_result("✅ B站已登录！如需重新登录请先 /B站登出")
            return

        yield event.plain_result("🔄 正在生成B站登录二维码...")

        # 申请二维码
        qr_data = await self.bili_login.generate_qrcode()
        if not qr_data:
            yield event.plain_result("❌ 生成二维码失败，请稍后重试")
            return

        qr_url = qr_data.get("url", "")
        qrcode_key = qr_data.get("qrcode_key", "")

        if not qr_url or not qrcode_key:
            yield event.plain_result("❌ 获取二维码数据失败")
            return

        # 本地生成二维码图片
        try:
            try:
                import segno
            except ImportError:
                yield event.plain_result("❌ 缺少 segno 依赖，请运行: pip install segno")
                return

            qr_filename = f"login_qr_{uuid.uuid4().hex[:8]}.png"
            qr_path = os.path.join(self.data_dir, qr_filename)
            qr = segno.make(qr_url)
            qr.save(qr_path, scale=10, border=4)
        except Exception as e:
            logger.error(f"生成二维码图片失败: {e}")
            yield event.plain_result(f"❌ 生成二维码图片失败: {e}")
            return

        # 发送二维码图片
        chain = [
            Plain("📱 请使用B站App扫描下方二维码登录\n⏳ 二维码有效期3分钟\n"),
            Image.fromFileSystem(qr_path),
        ]
        yield event.chain_result(chain)

        # 轮询登录结果
        result = await self.bili_login.do_login_flow(qrcode_key, timeout=180)

        if result["status"] == "success":
            # 更新 cookies
            self.bili_cookies = self.bili_login.get_cookies()
            # 重新初始化 NoteService
            self.note_service = NoteService(
                data_dir=self.data_dir,
                cookies=self.bili_cookies,
            )
            yield event.plain_result("✅ B站登录成功！现在可以使用所有功能了。")
        elif result["status"] == "expired":
            yield event.plain_result("⏰ 二维码已过期，请重新发送 /B站登录")
        elif result["status"] == "timeout":
            yield event.plain_result("⏰ 登录超时，请重新发送 /B站登录")
        else:
            yield event.plain_result("❌ 登录失败，请重新发送 /B站登录")

        # 清理二维码图片
        try:
            os.remove(qr_path)
        except Exception:
            pass

    @filter.command("B站登出", alias={"bili_logout", "哔哩登出"})
    async def bili_logout_cmd(self, event: AstrMessageEvent):
        """退出B站登录"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return

        if not self.bili_login.is_logged_in():
            yield event.plain_result("ℹ️ 当前未登录B站")
            return

        self.bili_login.logout()
        self.bili_cookies = {}
        yield event.plain_result("✅ 已退出B站登录")

    @filter.command("总结", alias={"BiliVideo", "视频总结", "总结"})
    async def generate_note_cmd(self, event: AstrMessageEvent):
        """手动为视频生成总结"""
        self._log("═══════ [总结命令] 开始处理 ═══════")

        if not self._check_access(event):
            self._log("[总结命令] 访问控制不通过, 结束")
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return

        # 从消息中提取 URL
        import re
        raw_msg = event.message_str or ""
        self._log(f"[总结命令] event.message_str = '{raw_msg}'")
        self._log(f"[总结命令] event.message_str type = {type(raw_msg)}")
        self._log(f"[总结命令] event.message_str repr = {repr(raw_msg)}")

        # 也尝试从 message_obj 中获取完整消息
        full_text = raw_msg
        try:
            if hasattr(event, 'message_obj') and event.message_obj:
                chain = event.message_obj.message
                self._log(f"[总结命令] message_obj.message 链长度 = {len(chain) if chain else 0}")
                for i, comp in enumerate(chain or []):
                    self._log(f"[总结命令] 消息组件[{i}]: type={type(comp).__name__}, str={str(comp)[:200]}")
                # 拼接所有 Plain 文本
                plain_texts = []
                for comp in (chain or []):
                    if hasattr(comp, 'text'):
                        plain_texts.append(comp.text)
                    elif isinstance(comp, str):
                        plain_texts.append(comp)
                if plain_texts:
                    full_text = " ".join(plain_texts)
                    self._log(f"[总结命令] 从 message_obj 拼接文本: '{full_text}'")
        except Exception as e:
            self._log(f"[总结命令] 解析 message_obj 异常: {e}")

        logger.info(f"总结命令收到消息: {raw_msg}")

        video_url = ""

        # 方式1: 从命令参数中取
        args = self._parse_args(raw_msg)
        self._log(f"[总结命令] 方式1 _parse_args 结果: '{args}'")
        if args:
            # 尝试直接取第一个参数作为URL
            first_arg = args.split()[0]
            self._log(f"[总结命令] 方式1 第一个参数: '{first_arg}'")
            if 'bilibili.com' in first_arg or 'b23.tv' in first_arg:
                video_url = first_arg
                self._log(f"[总结命令] 方式1 命中URL: '{video_url}'")

        # 方式2: 用正则从 raw_msg 中找 bilibili URL
        if not video_url:
            url_match = re.search(
                r'https?://(?:www\.)?bilibili\.com/video/[A-Za-z0-9/?=&_.]+',
                raw_msg
            )
            if url_match:
                video_url = url_match.group(0)
                self._log(f"[总结命令] 方式2 从raw_msg正则匹配: '{video_url}'")
            else:
                self._log("[总结命令] 方式2 raw_msg中未匹配到bilibili URL")

        # 方式3: 从 full_text (message_obj) 中找
        if not video_url and full_text != raw_msg:
            url_match = re.search(
                r'https?://(?:www\.)?bilibili\.com/video/[A-Za-z0-9/?=&_.]+',
                full_text
            )
            if url_match:
                video_url = url_match.group(0)
                self._log(f"[总结命令] 方式3 从full_text正则匹配: '{video_url}'")
            else:
                self._log("[总结命令] 方式3 full_text中未匹配到bilibili URL")

        # 方式4: 找 b23.tv 短链
        if not video_url:
            for text_src in [raw_msg, full_text]:
                short_match = re.search(r'https?://b23\.tv/\S+', text_src)
                if short_match:
                    video_url = short_match.group(0)
                    self._log(f"[总结命令] 方式4 短链匹配: '{video_url}'")
                    break
            if not video_url:
                self._log("[总结命令] 方式4 未匹配到 b23.tv 短链")

        # 方式5: 尝试从整条消息中找 BV 号
        if not video_url:
            bv_match = re.search(r'(BV[0-9A-Za-z]{10})', raw_msg + " " + full_text)
            if bv_match:
                video_url = f"https://www.bilibili.com/video/{bv_match.group(1)}"
                self._log(f"[总结命令] 方式5 从BV号构建URL: '{video_url}'")
            else:
                self._log("[总结命令] 方式5 未找到BV号")

        if not video_url:
            self._log("[总结命令] 所有方式均未提取到URL, 返回错误")
            self._log("═══════ [总结命令] 结束(无URL) ═══════")
            yield event.plain_result(
                "❌ 请提供视频链接\n用法: /总结 <B站视频链接>\n"
                "示例: /总结 https://www.bilibili.com/video/BV1xx..."
            )
            return

        video_url = video_url.rstrip('>')
        platform = detect_platform(video_url)
        self._log(f"[总结命令] 最终URL='{video_url}', platform='{platform}'")
        if platform != "bilibili":
            self._log("═══════ [总结命令] 结束(非B站) ═══════")
            yield event.plain_result("❌ 目前仅支持B站视频链接")
            return

        yield event.plain_result("⏳ 正在生成总结，请稍候（可能需要1-3分钟）...")

        self._log(f"[总结命令] 调用 _generate_note: {video_url}")
        note = await self._generate_note(video_url)
        self._log(f"[总结命令] 总结生成完成, 长度={len(note) if note else 0}")

        # 渲染总结（图片或文本）
        result = self._render_and_get_chain(note)
        self._log(f"[总结命令] 输出模式: {'图片' if isinstance(result, list) else '文本'}")

        # 合并转发模式
        if self.config.get("enable_forward_message", False):
            self._log("[总结命令] 使用合并转发模式发送")
            # 提取 BV 号以获取视频信息
            bv_match = re.search(r'(BV[0-9A-Za-z]{10})', video_url)
            video_info = None
            if bv_match:
                try:
                    video_info = await get_video_info(
                        bv_match.group(1), cookies=self.bili_cookies
                    )
                except Exception as e:
                    self._log(f"[总结命令] 获取视频信息失败: {e}")

            if video_info:
                forward_nodes = self._build_forward_nodes(video_info, result)
                self._log("═══════ [总结命令] 结束(合并转发) ═══════")
                yield event.chain_result([forward_nodes])
                return
            else:
                self._log("[总结命令] 视频信息获取失败, 回退到普通模式")

        # 普通模式发送
        self._log("═══════ [总结命令] 结束(成功) ═══════")
        if isinstance(result, list):
            yield event.chain_result(result)
        else:
            yield event.plain_result(result)

    @filter.command("最新视频", alias={"latest"})
    async def latest_video_cmd(self, event: AstrMessageEvent):
        """获取UP主最新视频并生成总结"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return
        args = self._parse_args(event.message_str)
        if not args:
            yield event.plain_result("❌ 请提供UP主UID、空间链接或昵称\n用法: /最新视频 <UP主UID或昵称>")
            return

        mid = extract_bilibili_mid(args)
        if not mid:
            # 尝试按名称搜索UP主
            yield event.plain_result(f"🔍 正在搜索UP主: {args}...")
            search_result = await search_up_by_name(args, cookies=self.bili_cookies)
            if search_result:
                mid = search_result["mid"]
                yield event.plain_result(f"✅ 找到UP主【{search_result['name']}】(UID:{mid})")
            else:
                yield event.plain_result(
                    "❌ 无法识别UP主\n"
                    "支持: 纯数字UID、空间链接、或UP主昵称"
                )
                return

        yield event.plain_result(f"⏳ 正在获取UP主 (UID:{mid}) 的最新视频...")

        videos = await get_latest_videos(mid, count=1, cookies=self.bili_cookies)
        if not videos:
            yield event.plain_result("❌ 未找到该UP主的视频")
            return

        video = videos[0]
        video_url = f"https://www.bilibili.com/video/{video['bvid']}"

        yield event.plain_result(
            f"📺 找到最新视频: {video['title']}\n⏳ 正在生成总结..."
        )

        note = await self._generate_note(video_url)
        result = self._render_and_get_chain(note)

        # 合并转发模式
        if self.config.get("enable_forward_message", False):
            try:
                video_info = await get_video_info(
                    video["bvid"], cookies=self.bili_cookies
                )
            except Exception:
                video_info = None

            if video_info:
                forward_nodes = self._build_forward_nodes(video_info, result)
                yield event.chain_result([forward_nodes])
                return

        if isinstance(result, list):
            yield event.chain_result(result)
        else:
            yield event.plain_result(result)

    @filter.command("订阅", alias={"subscribe", "关注UP"})
    async def subscribe_cmd(self, event: AstrMessageEvent):
        """订阅UP主"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return
        args = self._parse_args(event.message_str)
        if not args:
            yield event.plain_result("❌ 请提供UP主UID、空间链接或昵称\n用法: /订阅 <UP主UID或昵称>")
            return

        search_result = None
        mid = extract_bilibili_mid(args)
        if not mid:
            # 尝试按名称搜索UP主
            yield event.plain_result(f"🔍 正在搜索UP主: {args}...")
            search_result = await search_up_by_name(args, cookies=self.bili_cookies)
            if search_result:
                mid = search_result["mid"]
                yield event.plain_result(f"✅ 找到UP主【{search_result['name']}】(UID:{mid})")
            else:
                yield event.plain_result(
                    "❌ 无法识别UP主\n"
                    "支持: 纯数字UID、空间链接、或UP主昵称"
                )
                return

        # 检查订阅上限
        max_subs = self.config.get("max_subscriptions", 20)
        origin = event.unified_msg_origin
        current_count = self.subscription_mgr.get_subscription_count(origin)
        if current_count >= max_subs:
            yield event.plain_result(f"❌ 已达到最大订阅数 ({max_subs})")
            return

        # 获取 UP主 信息（失败时多级回退）
        up_info = await get_up_info(mid, cookies=self.bili_cookies)
        if not up_info:
            if search_result and search_result.get("name"):
                logger.warning(f"get_up_info 失败 (UID:{mid})，回退使用搜索结果名称")
            else:
                # 尝试从最新视频中获取UP主名称
                logger.warning(f"get_up_info 失败 (UID:{mid})，尝试从视频获取UP主名称")
                try:
                    videos = await get_latest_videos(mid, count=1, cookies=self.bili_cookies)
                    if videos and videos[0].get("bvid"):
                        vi = await get_video_info(videos[0]["bvid"], cookies=self.bili_cookies)
                        if vi and vi.get("owner_name"):
                            search_result = {"mid": mid, "name": vi["owner_name"]}
                            logger.info(f"从视频获取到UP主名称: {search_result['name']}")
                        else:
                            search_result = {"mid": mid, "name": f"UP主_{mid}"}
                            logger.warning(f"无法获取UP主名称，使用 UID 兜底")
                    else:
                        # 最后的兜底：使用 UID 作为名称
                        search_result = {"mid": mid, "name": f"UP主_{mid}"}
                        logger.warning(f"无法获取UP主名称，使用 UID 兜底")
                except Exception as e:
                    search_result = {"mid": mid, "name": f"UP主_{mid}"}
                    logger.warning(f"获取视频列表失败: {e}，使用 UID 兜底")

        name = up_info["name"] if up_info else search_result["name"]

        # 添加订阅
        success = self.subscription_mgr.add_subscription(origin, mid, name)
        if success:
            # 记录最新视频 BVID，避免重复推送已有视频
            videos = await get_latest_videos(mid, count=1, cookies=self.bili_cookies)
            if videos:
                self.subscription_mgr.update_last_video(origin, mid, videos[0]["bvid"])

            yield event.plain_result(
                f"✅ 已订阅 UP主【{name}】(UID:{mid})\n"
                f"有新视频时将自动推送总结"
            )
        else:
            yield event.plain_result(f"⚠️ 已经订阅了 UP主【{name}】(UID:{mid})")

    @filter.command("取消订阅", alias={"unsubscribe", "取关UP"})
    async def unsubscribe_cmd(self, event: AstrMessageEvent):
        """取消订阅UP主"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return
        args = self._parse_args(event.message_str)
        if not args:
            yield event.plain_result("❌ 请提供UP主UID、空间链接或昵称\n用法: /取消订阅 <UP主UID或昵称>")
            return

        mid = extract_bilibili_mid(args)
        if not mid:
            # 尝试按名称搜索UP主
            yield event.plain_result(f"🔍 正在搜索UP主: {args}...")
            search_result = await search_up_by_name(args, cookies=self.bili_cookies)
            if search_result:
                mid = search_result["mid"]
                yield event.plain_result(f"✅ 找到UP主【{search_result['name']}】(UID:{mid})")
            else:
                yield event.plain_result(
                    "❌ 无法识别UP主\n"
                    "支持: 纯数字UID、空间链接、或UP主昵称"
                )
                return

        origin = event.unified_msg_origin
        success = self.subscription_mgr.remove_subscription(origin, mid)

        if success:
            yield event.plain_result(f"✅ 已取消订阅 (UID:{mid})")
        else:
            yield event.plain_result(f"⚠️ 未找到该订阅 (UID:{mid})")

    @filter.command("订阅列表", alias={"sublist", "订阅列表查看"})
    async def list_subscriptions_cmd(self, event: AstrMessageEvent):
        """查看订阅列表"""
        origin = event.unified_msg_origin
        subs = self.subscription_mgr.get_subscriptions(origin)

        if not subs:
            yield event.plain_result("📋 当前没有订阅任何UP主\n使用 /订阅 <UID或昵称> 添加订阅")
            return

        lines = ["📋 当前订阅列表:"]
        lines.append("━━━━━━━━━━━━━━━━━━━")
        for i, up in enumerate(subs, 1):
            lines.append(f"  {i}. {up['name']} (UID:{up['mid']})")

        lines.append(f"\n共 {len(subs)} 个订阅")
        yield event.plain_result("\n".join(lines))

    @filter.command("检查更新", alias={"check", "手动检查"})
    async def manual_check_cmd(self, event: AstrMessageEvent):
        """手动触发一次订阅检查"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return

        origin = event.unified_msg_origin
        subs = self.subscription_mgr.get_subscriptions(origin)

        if not subs:
            yield event.plain_result("📋 当前没有订阅任何UP主，无法检查更新")
            return

        yield event.plain_result(
            f"🔍 正在检查 {len(subs)} 个UP主的更新...\n"
            f"这可能需要一些时间，请耐心等待"
        )

        found_new = 0
        for up in subs:
            try:
                mid = up["mid"]
                last_bvid = up.get("last_bvid", "")

                videos = await get_latest_videos(mid, count=1, cookies=self.bili_cookies)
                if not videos:
                    continue

                latest = videos[0]
                latest_bvid = latest["bvid"]

                if latest_bvid == last_bvid:
                    continue  # 没有新视频

                if not last_bvid:
                    # 首次检查，只记录不推送
                    self.subscription_mgr.update_last_video(origin, mid, latest_bvid)
                    continue

                # 有新视频！
                found_new += 1
                yield event.plain_result(
                    f"🔔 UP主【{up['name']}】有新视频!\n"
                    f"📺 {latest['title']}\n"
                    f"⏳ 正在生成总结..."
                )

                video_url = f"https://www.bilibili.com/video/{latest_bvid}"
                note = await self._generate_note(video_url)
                result = self._render_and_get_chain(note)
                if isinstance(result, list):
                    yield event.chain_result(result)
                else:
                    yield event.plain_result(result)

                # 更新已推送记录
                self.subscription_mgr.update_last_video(origin, mid, latest_bvid)

                await asyncio.sleep(2)  # 避免请求过快
            except Exception as e:
                logger.error(f"手动检查UP主 {up.get('name', '?')} 失败: {e}")

        if found_new == 0:
            yield event.plain_result("✅ 检查完成，所有订阅的UP主暂无新视频")
        else:
            yield event.plain_result(f"✅ 检查完成，共发现 {found_new} 个新视频")

    # ==================== 推送目标管理 ====================

    def _detect_platform_prefix(self, origin: str) -> str:
        """
        从 unified_msg_origin 中提取平台前缀
        例如 'aiocqhttp:GroupMessage:123' -> 'aiocqhttp'
        """
        parts = origin.split(':')
        return parts[0] if parts else ''

    def _build_group_origin(self, origin: str, group_id: str) -> str:
        """根据当前平台构建群消息 origin"""
        prefix = self._detect_platform_prefix(origin)
        return f"{prefix}:GroupMessage:{group_id}"

    def _build_user_origin(self, origin: str, user_id: str) -> str:
        """根据当前平台构建私聊 origin"""
        prefix = self._detect_platform_prefix(origin)
        return f"{prefix}:FriendMessage:{user_id}"

    @filter.command("添加推送群", alias={"add_push_group"})
    async def add_push_group_cmd(self, event: AstrMessageEvent):
        """添加QQ群到推送列表"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return
        args = self._parse_args(event.message_str)
        if not args or not args.strip().isdigit():
            yield event.plain_result("❌ 请提供QQ群号\n用法: /添加推送群 <群号>")
            return

        group_id = args.strip()
        target_origin = self._build_group_origin(event.unified_msg_origin, group_id)
        success = self.subscription_mgr.add_push_target(target_origin, f"群{group_id}")
        if success:
            yield event.plain_result(f"✅ 已添加推送目标: 群 {group_id}")
        else:
            yield event.plain_result(f"⚠️ 群 {group_id} 已在推送列表中")

    @filter.command("添加推送号", alias={"add_push_user"})
    async def add_push_user_cmd(self, event: AstrMessageEvent):
        """添加QQ号到推送列表"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return
        args = self._parse_args(event.message_str)
        if not args or not args.strip().isdigit():
            yield event.plain_result("❌ 请提供QQ号\n用法: /添加推送号 <QQ号>")
            return

        user_id = args.strip()
        target_origin = self._build_user_origin(event.unified_msg_origin, user_id)
        success = self.subscription_mgr.add_push_target(target_origin, f"QQ{user_id}")
        if success:
            yield event.plain_result(f"✅ 已添加推送目标: QQ {user_id}")
        else:
            yield event.plain_result(f"⚠️ QQ {user_id} 已在推送列表中")

    @filter.command("推送列表", alias={"push_list", "推送目标"})
    async def push_list_cmd(self, event: AstrMessageEvent):
        """查看推送目标列表"""
        targets = self.subscription_mgr.get_push_targets()
        if not targets:
            yield event.plain_result(
                "📋 当前没有配置推送目标\n"
                "使用 /添加推送群 <群号> 或 /添加推送号 <QQ号> 添加\n"
                "⚠️ 未配置推送目标时，总结将推送到发起订阅的群"
            )
            return

        lines = ["📋 当前推送目标:"]
        lines.append("━━━━━━━━━━━━━━━━━━━")
        for i, t in enumerate(targets, 1):
            lines.append(f"  {i}. {t['label']}")
        lines.append(f"\n共 {len(targets)} 个推送目标")
        yield event.plain_result("\n".join(lines))

    @filter.command("移除推送", alias={"remove_push", "删除推送"})
    async def remove_push_cmd(self, event: AstrMessageEvent):
        """移除推送目标"""
        if not self._check_access(event):
            yield event.plain_result("⛔ 你没有权限使用此插件")
            return
        args = self._parse_args(event.message_str)
        if not args:
            yield event.plain_result("❌ 请提供要移除的群号或QQ号\n用法: /移除推送 <群号或QQ号>")
            return

        target_id = args.strip()
        # 尝试按 label 匹配
        label_group = f"群{target_id}"
        label_user = f"QQ{target_id}"
        success = self.subscription_mgr.remove_push_target(label_group)
        if not success:
            success = self.subscription_mgr.remove_push_target(label_user)
        if not success:
            success = self.subscription_mgr.remove_push_target(target_id)

        if success:
            yield event.plain_result(f"✅ 已移除推送目标: {target_id}")
        else:
            yield event.plain_result(f"⚠️ 未找到该推送目标: {target_id}")

    # ==================== 核心逻辑 ====================

    async def _generate_note(self, video_url: str) -> str:
        """生成总结的统一调用入口"""
        self._log("═══════ [生成总结] 开始 ═══════")
        style = self.config.get("note_style", "detailed")
        enable_link = self.config.get("enable_link", True)
        enable_summary = self.config.get("enable_summary", True)
        quality = self.config.get("download_quality", "fast")
        max_length = self.config.get("max_note_length", 3000)
        self._log(
            f"[生成总结] 参数: url={video_url}, style={style}, "
            f"enable_link={enable_link}, enable_summary={enable_summary}, "
            f"quality={quality}, max_length={max_length}"
        )

        try:
            result = await self.note_service.generate_note(
                video_url=video_url,
                llm_ask_func=self._ask_llm,
                style=style,
                enable_link=enable_link,
                enable_summary=enable_summary,
                quality=quality,
                max_length=max_length,
            )
            self._log(f"[生成总结] 完成, 结果长度={len(result) if result else 0}")
            self._log("═══════ [生成总结] 结束 ═══════")
            return result
        except Exception as e:
            self._log(f"[生成总结] 异常: {e}")
            self._log("═══════ [生成总结] 结束(异常) ═══════")
            logger.error(f"总结生成异常: {e}", exc_info=True)
            return f"❌ 总结生成失败: {str(e)}"

    async def _ask_llm(self, prompt: str) -> str:
        """根据配置调用 LLM（AstrBot 内置 或 OpenAI 兼容 API）"""
        if self.llm_provider == "openai_compatible":
            return await self._ask_llm_openai_compatible(prompt)
        return await self._ask_llm_astrbot(prompt)

    async def _ask_llm_astrbot(self, prompt: str) -> str:
        """调用 AstrBot 内置 LLM"""
        try:
            self._log(f"[AskLLM/AstrBot] prompt 长度={len(prompt)}, 前100字: {prompt[:100]}...")
            provider = self.context.get_using_provider()
            self._log(f"[AskLLM/AstrBot] provider={type(provider).__name__ if provider else 'None'}")
            if not provider:
                return "❌ 未配置 LLM Provider，请在 AstrBot 设置中配置"

            response = await provider.text_chat(
                prompt=prompt,
                session_id="BiliVideo_plugin",
            )
            self._log(f"[AskLLM/AstrBot] response type={type(response).__name__}")

            if hasattr(response, 'completion_text'):
                result = response.completion_text
                self._log(f"[AskLLM/AstrBot] 使用 completion_text, 长度={len(result) if result else 0}")
                return result
            elif isinstance(response, str):
                self._log(f"[AskLLM/AstrBot] response 是 str, 长度={len(response)}")
                return response
            else:
                self._log(f"[AskLLM/AstrBot] response 转 str")
                return str(response)

        except Exception as e:
            logger.error(f"LLM 调用失败 (AstrBot): {e}", exc_info=True)
            return f"❌ LLM 调用失败: {str(e)}"

    async def _ask_llm_openai_compatible(self, prompt: str) -> str:
        """调用 OpenAI 兼容 API"""
        try:
            if not self.llm_api_base or not self.llm_api_key:
                return "❌ 请先配置 llm_api_base 和 llm_api_key"

            self._log(f"[AskLLM/OpenAI] prompt 长度={len(prompt)}, model={self.llm_model}")
            url = f"{self.llm_api_base}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.llm_model,
                "messages": [{"role": "user", "content": prompt}],
            }

            import aiohttp as _aiohttp
            timeout = _aiohttp.ClientTimeout(total=120)
            async with _aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(f"OpenAI 兼容 API 返回 HTTP {resp.status}: {body[:500]}")
                        return f"❌ LLM API 返回错误 (HTTP {resp.status})"

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    self._log(f"[AskLLM/OpenAI] 响应长度={len(content)}")
                    return content

        except Exception as e:
            logger.error(f"LLM 调用失败 (OpenAI Compatible): {e}", exc_info=True)
            return f"❌ LLM 调用失败: {str(e)}"

    # ==================== 定时任务 ====================

    async def _scheduled_check_loop(self):
        """定时检查订阅UP主的新视频"""
        await asyncio.sleep(10)  # 启动后等待10秒再开始

        while self._running:
            try:
                await self._check_new_videos()
            except Exception as e:
                logger.error(f"定时检查异常: {e}", exc_info=True)

            interval = self.config.get("check_interval_minutes", 30)
            await asyncio.sleep(interval * 60)

    async def _check_new_videos(self):
        """检查所有订阅是否有新视频"""
        all_subs = self.subscription_mgr.get_all_subscriptions()

        if not all_subs:
            return

        logger.info(f"开始定时检查，共 {len(all_subs)} 个会话的订阅")

        for origin, up_list in all_subs.items():
            for up in up_list:
                try:
                    await self._check_up_new_video(origin, up)
                    await asyncio.sleep(2)  # 避免请求过快
                except Exception as e:
                    logger.error(f"检查UP主 {up['name']} 新视频失败: {e}")

    async def _check_up_new_video(self, origin: str, up: dict):
        """检查单个UP主是否有新视频"""
        mid = up["mid"]
        last_bvid = up.get("last_bvid", "")

        videos = await get_latest_videos(mid, count=1, cookies=self.bili_cookies)
        if not videos:
            return

        latest = videos[0]
        latest_bvid = latest["bvid"]

        if latest_bvid == last_bvid:
            return  # 没有新视频

        if not last_bvid:
            # 首次检查，只记录不推送
            self.subscription_mgr.update_last_video(origin, mid, latest_bvid)
            return

        # 有新视频！
        logger.info(f"UP主 {up['name']} 有新视频: {latest['title']}")

        video_url = f"https://www.bilibili.com/video/{latest_bvid}"
        push_header = f"🔔 UP主【{up['name']}】发布了新视频!\n"

        if not self.config.get("auto_push_summary", True):
            # 仅推送视频基本信息，不进行转写和 LLM 总结
            import time as _time
            lines = [push_header + f"📺 {latest['title']}"]
            if latest.get("description"):
                desc = latest["description"]
                if len(desc) > 100:
                    desc = desc[:100] + "..."
                lines.append(f"📝 简介: {desc}")
            if latest.get("pubdate"):
                try:
                    pub_str = _time.strftime('%Y-%m-%d %H:%M', _time.localtime(latest["pubdate"]))
                    lines.append(f"📅 发布: {pub_str}")
                except Exception:
                    pass
            lines.append(f"🔗 {video_url}")

            chain_components = []
            pic_url = latest.get("pic", "")
            if pic_url:
                if pic_url.startswith("//"):
                    pic_url = "https:" + pic_url
                chain_components.append(Image.fromURL(pic_url))
            chain_components.append(Plain("\n".join(lines)))
        else:
            # 生成总结
            note = await self._generate_note(video_url)

            # 渲染总结
            result = self._render_and_get_chain(note)

            # 合并转发模式
            if self.config.get("enable_forward_message", False):
                try:
                    video_info = await get_video_info(
                        latest_bvid, cookies=self.bili_cookies
                    )
                except Exception:
                    video_info = None

                if video_info:
                    forward_nodes = self._build_forward_nodes(video_info, result)
                    push_header_node = Node(
                        content=[Plain(f"🔔 UP主【{up['name']}】发布了新视频!")],
                        name="BiliVideo 助手",
                        uin="0",
                    )
                    # 在转发消息头部插入推送提醒
                    forward_nodes.nodes.insert(0, push_header_node)
                    chain_components = [forward_nodes]
                else:
                    # 回退到普通模式
                    if isinstance(result, list):
                        chain_components = [Plain(push_header)] + result
                    else:
                        chain_components = [Plain(push_header + "━━━━━━━━━━━━━━━━━━━\n\n" + result)]
            else:
                # 普通推送模式
                if isinstance(result, list):
                    chain_components = [Plain(push_header)] + result
                else:
                    chain_components = [Plain(push_header + "━━━━━━━━━━━━━━━━━━━\n\n" + result)]

        # 获取推送目标：优先使用配置的推送目标，否则推到订阅来源
        push_origins = self.subscription_mgr.get_push_origins()
        if not push_origins:
            push_origins = [origin]

        for target in push_origins:
            try:
                mc = MessageChain(chain=chain_components)
                await self.context.send_message(target, mc)
                logger.info(f"已推送新视频总结给 {target}")
            except Exception as e:
                logger.error(f"推送消息到 {target} 失败: {e}")

        # 更新已推送记录
        self.subscription_mgr.update_last_video(origin, mid, latest_bvid)

    # ==================== 生命周期 ====================

    async def terminate(self):
        """插件卸载时停止定时任务"""
        self._running = False
        if self._check_task and not self._check_task.done():
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

        logger.info("BiliVideo 视频总结插件已卸载")
