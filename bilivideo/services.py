"""Composition root for the plugin.

`BiliVideoServices` wires every component together and exposes a single
object that the AstrBot Star class can poke without knowing about the
underlying details.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from .access.cooldown import CooldownTracker
from .access.inflight import InflightDeduper
from .api.client import BilibiliHTTPClient
from .auth.cookies import CookieJar
from .auth.qrlogin import QRLoginService
from .auth.youtube_cookies import YouTubeCookieStore
from .core.config import PluginConfig
from .core.logging import get_logger
from .core.runtime_state import RuntimeState
from .downloader.ytdlp_downloader import YtDlpDownloader
from .llm.provider import DisabledLLMProvider, LLMProvider, build_provider
from .render.chain import RenderChain
from .search import SearchService
from .subscription.manager import SubscriptionManager
from .subscription.scheduler import CheckScheduler
from .summarize.orchestrator import SummaryOrchestrator
from .transcription.bcut_provider import BCutTranscriber
from .transcription.pipeline import TranscriptPipeline


class BiliVideoServices:
    """All plugin-level singletons assembled in one place.

    Construction is intentionally synchronous so the Star class can build
    services in `__init__` and tests can mount everything without an event
    loop.
    """

    def __init__(
        self,
        *,
        config: PluginConfig,
        data_dir: str,
        astrbot_context: object | None = None,
    ) -> None:
        self.logger = get_logger("BiliVideo", debug_enabled=config.debug_mode)
        self.config = config
        self.data_dir = data_dir
        self.astrbot_context = astrbot_context
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        Path(data_dir, "images").mkdir(parents=True, exist_ok=True)
        self.runtime_state = RuntimeState(data_dir)

        # Auth + cookies
        self.cookies = CookieJar(data_dir)
        self.qrlogin = QRLoginService()

        # Networking
        self.http_client = BilibiliHTTPClient(self.cookies.get())

        # Download / transcription
        # YouTube cookies (experimental): captured in-chat via /YT登录 and saved
        # by the bot, so VPS users never touch the filesystem. The downloader
        # reads this jar for YouTube URLs.
        self.youtube_cookies = YouTubeCookieStore(data_dir)
        self.youtube_cookies_file = self.youtube_cookies.path
        self.downloader = YtDlpDownloader(
            data_dir=str(Path(data_dir) / "audio"),
            cookies=self.cookies.get(),
            youtube_cookies_file=self.youtube_cookies_file,
        )
        self.transcriber = BCutTranscriber()
        self.pipeline = TranscriptPipeline(self.downloader, self.transcriber)

        # LLM (runtime model override takes precedence over the config default)
        initial_provider_id = (
            self.runtime_state.get_str("llm_provider_id") or config.llm_provider_id
        )
        self.llm: LLMProvider = build_provider(
            config, astrbot_context=astrbot_context, provider_id=initial_provider_id
        )
        if isinstance(self.llm, DisabledLLMProvider):
            self.logger.warning(
                "openai_compatible credentials missing; LLM disabled but plugin startup continues"
            )

        # Summary + render
        self.orchestrator = SummaryOrchestrator(
            config=config,
            llm=self.llm,
            pipeline=self.pipeline,
            http_client=self.http_client,
        )
        self.renderer = RenderChain(
            output_dir=str(Path(data_dir) / "images"),
            image_width=config.image_width,
        )
        self.logger.info(
            f"render backends available: {', '.join(self.renderer.available_backends) or '(none)'}"
        )

        # Search service for AI tools
        self.search_service = SearchService(
            data_dir=data_dir,
            http_client=self.http_client,
            pipeline=self.pipeline,
        )

        # Subscription / scheduler (callback wired later by Star)
        self.subscription_manager = SubscriptionManager(data_dir)
        self.scheduler: CheckScheduler | None = None

        # Anti-spam
        self.cooldown = CooldownTracker(window_seconds=config.user_cooldown_seconds)
        self.inflight: InflightDeduper[str, object] = InflightDeduper()

        # Run-time mutable flags
        runtime_detect = self.runtime_state.get_bool("enable_miniapp_detect")
        self.enable_miniapp_detect = (
            runtime_detect if runtime_detect is not None else config.enable_miniapp_detect
        )

        # Track in-flight long jobs (e.g. AI search download)
        self._download_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # cookie/login helpers used by handlers
    # ------------------------------------------------------------------
    def update_cookies(self, cookies: dict[str, str] | None) -> None:
        if cookies is None:
            self.cookies.clear()
        else:
            self.cookies.save(cookies)
        active = self.cookies.get()
        self.http_client.update_cookies(active)
        self.downloader.update_cookies(active)

    def is_logged_in(self) -> bool:
        return self.cookies.is_logged_in()

    # ------------------------------------------------------------------
    # download task helpers
    # ------------------------------------------------------------------
    def replace_download_task(self, task: asyncio.Task) -> None:
        if self._download_task and not self._download_task.done():
            self._download_task.cancel()
        self._download_task = task

    @property
    def download_task(self) -> asyncio.Task | None:
        return self._download_task

    async def shutdown(self) -> None:
        if self.scheduler is not None:
            await self.scheduler.stop()
        if self._download_task and not self._download_task.done():
            self._download_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._download_task
        await self.http_client.close()
