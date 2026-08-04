"""End-to-end note generation pipeline.

Orchestrates:
  1. Fetch transcript via the pipeline (subtitle preferred, BCut fallback).
  2. Build prompt and ask the configured LLM.
  3. Post-process (timestamp markers, smart truncation).
  4. Clean up downloaded audio (if any).

Each step is wrapped in fine-grained try/except blocks so we can surface
specific user-facing errors (`BiliVideoError.user_message`).
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

from ..api.client import BilibiliHTTPClient
from ..api.endpoints import get_video_info
from ..cache.lru_ttl import LRUTTLCache
from ..core.config import PluginConfig
from ..core.constants import LLM_CHAT_TIMEOUT_SECONDS, SUMMARY_CACHE_MAX, SUMMARY_CACHE_TTL_SECONDS
from ..core.exceptions import BiliVideoError
from ..core.logging import get_logger
from ..core.types import VideoInfo
from ..llm.prompts import build_prompt
from ..llm.provider import LLMProvider, StructuredSummaryProvider
from ..llm.structured_summary import (
    SUMMARY_FORMAT_VERSION,
    StructuredSummaryError,
    parse_structured_summary,
    structured_summary_to_markdown,
)
from ..parsing.url_extractor import extract_bvid
from ..transcription.pipeline import TranscriptPipeline
from .post_process import replace_timestamp_markers, smart_truncate

logger = get_logger("BiliVideo/Summary")


@dataclass(slots=True)
class NoteResult:
    markdown: str
    video_info: VideoInfo | None
    used_subtitle: bool


class SummaryOrchestrator:
    """Coordinates pipeline + LLM + post-processing for a single URL."""

    def __init__(
        self,
        *,
        config: PluginConfig,
        llm: LLMProvider,
        pipeline: TranscriptPipeline,
        http_client: BilibiliHTTPClient,
    ) -> None:
        self._config = config
        self._llm = llm
        self._pipeline = pipeline
        self._http = http_client
        self._cache: LRUTTLCache[str, NoteResult] = LRUTTLCache(
            max_size=SUMMARY_CACHE_MAX, ttl_seconds=SUMMARY_CACHE_TTL_SECONDS
        )

    async def clear_cache(self) -> None:
        await self._cache.clear()

    async def generate(self, video_url: str) -> NoteResult:
        """Run the pipeline under the configured processing timeout."""

        timeout = self._config.processing_timeout
        if timeout and timeout > 0:
            try:
                return await asyncio.wait_for(self._generate(video_url), timeout=timeout)
            except asyncio.TimeoutError as exc:
                logger.warning(f"summary generation timed out after {timeout}s: {video_url}")
                raise BiliVideoError(
                    f"processing timeout after {timeout}s",
                    user_message="❌ 处理超时,请稍后重试或换一个视频",
                ) from exc
        return await self._generate(video_url)

    async def _generate(self, video_url: str) -> NoteResult:
        bvid = extract_bvid(video_url)
        cache_key = self._summary_cache_key(bvid) if bvid else None
        if cache_key:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.info(f"summary cache hit for {bvid}")
                return cached
        info: VideoInfo | None = None
        if bvid:
            try:
                info = await get_video_info(self._http, bvid)
            except BiliVideoError as exc:
                logger.warning(f"video info lookup failed for {bvid}: {exc}")

        try:
            output = await self._pipeline.fetch(
                video_url,
                prefer_subtitle=self._config.prefer_subtitle,
                quality=self._config.download_quality,
                subtitle_langs=self._config.subtitle_langs,
            )
        except BiliVideoError:
            raise
        except Exception as exc:
            logger.error(f"transcript pipeline failed: {exc}", exc_info=True)
            raise BiliVideoError(
                f"transcript pipeline error: {exc}",
                user_message="❌ 转写流程异常,请稍后重试",
            ) from exc

        title = (output.audio.title if output.audio else (info.title if info else "")) or "视频总结"
        tags = ""
        if output.audio:
            raw_tags = (output.audio.raw_info or {}).get("tags")
            if isinstance(raw_tags, list):
                tags = ", ".join(str(t) for t in raw_tags)
            elif isinstance(raw_tags, str):
                tags = raw_tags

        prompt_args = {
            "title": title,
            "segments": output.transcript.segments,
            "tags": tags,
            "style": self._config.note_style,
            "enable_link": self._config.enable_link,
            "enable_summary": self._config.enable_summary,
        }
        legacy_prompt = build_prompt(**prompt_args, structured_output=False)
        structured_prompt = build_prompt(**prompt_args, structured_output=True)

        try:
            markdown = await asyncio.wait_for(
                self._request_markdown(
                    legacy_prompt=legacy_prompt,
                    structured_prompt=structured_prompt,
                    max_timestamp_seconds=max(
                        0,
                        math.ceil(
                            max(
                                (segment.end for segment in output.transcript.segments),
                                default=0,
                            )
                        ),
                    ),
                ),
                timeout=LLM_CHAT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise BiliVideoError(
                f"LLM chat timed out after {LLM_CHAT_TIMEOUT_SECONDS}s",
                user_message="❌ AI 总结超时:当前对话模型无响应,请在 AstrBot 检查或更换对话模型",
            ) from exc
        finally:
            self._pipeline.cleanup_audio(output.audio)

        if not markdown:
            raise BiliVideoError("empty LLM output", user_message="❌ AI 返回内容为空,请重试")

        if self._config.enable_link:
            markdown = replace_timestamp_markers(markdown)

        markdown = smart_truncate(markdown, self._config.max_note_length)

        result = NoteResult(
            markdown=markdown,
            video_info=info,
            used_subtitle=output.audio is None,
        )
        if cache_key:
            await self._cache.set(cache_key, result)
        return result

    async def _request_markdown(
        self,
        *,
        legacy_prompt: str,
        structured_prompt: str,
        max_timestamp_seconds: int,
    ) -> str:
        if self._config.enable_link and isinstance(self._llm, StructuredSummaryProvider):
            attempt = await self._llm.chat_structured_summary(
                structured_prompt,
                include_ai_summary=self._config.enable_summary,
                session_id="BiliVideo_plugin",
            )
            if attempt.arguments is not None:
                try:
                    summary = parse_structured_summary(
                        attempt.arguments,
                        max_timestamp_seconds=max_timestamp_seconds,
                        require_ai_summary=self._config.enable_summary,
                    )
                except StructuredSummaryError as exc:
                    logger.warning(f"structured summary rejected; using Markdown fallback: {exc}")
                else:
                    logger.info("structured summary accepted from AstrBot tool call")
                    return structured_summary_to_markdown(summary)
            if attempt.fallback_text:
                logger.info("AstrBot returned text instead of a tool call; using it as fallback")
                return attempt.fallback_text

        return await self._llm.chat(legacy_prompt, session_id="BiliVideo_plugin")

    def _summary_cache_key(self, bvid: str) -> str:
        provider_identity = type(self._llm).__name__
        cache_identity = getattr(self._llm, "cache_identity", None)
        if callable(cache_identity):
            try:
                provider_identity = str(cache_identity())
            except Exception as exc:
                logger.debug(f"provider cache identity unavailable: {exc}")
        selected_provider = str(
            getattr(self._llm, "provider_id", "") or self._config.llm_provider_id
        )
        return "|".join(
            (
                SUMMARY_FORMAT_VERSION,
                bvid,
                self._config.llm_provider,
                provider_identity,
                selected_provider,
                self._config.llm_model,
                self._config.note_style,
                f"link={int(self._config.enable_link)}",
                f"summary={int(self._config.enable_summary)}",
                f"limit={self._config.max_note_length}",
            )
        )
