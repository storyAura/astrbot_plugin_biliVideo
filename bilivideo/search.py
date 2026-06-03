"""Search + batch transcription service for AI-tool use cases.

Replaces the previous `services/search_service.py` with cleaner types and
proper async/await throughout. Used by the `bilibili_search_*` AI tools.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from .api.client import BilibiliHTTPClient
from .api.endpoints import get_video_info
from .core.exceptions import BiliVideoError
from .core.logging import get_logger
from .core.types import TranscriptResult, VideoInfo
from .messaging.chunker import format_count
from .transcription.pipeline import TranscriptPipeline

logger = get_logger("BiliVideo/Search")

ProgressCallback = Callable[[dict], Awaitable[None]]
_SAFE_NAME_RE = re.compile(r"[\\/:*?\"<>|]")


@dataclass(slots=True)
class VideoTranscriptResult:
    bvid: str
    info: VideoInfo | None = None
    transcript: str = ""
    success: bool = False
    error: str = ""


@dataclass(slots=True)
class BatchResult:
    folder_name: str
    folder_path: Path
    videos: list[VideoTranscriptResult] = field(default_factory=list)
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0

    def to_summary(self) -> str:
        elapsed = self.finished_at - self.started_at if self.finished_at else 0
        lines = [
            f"folder: {self.folder_name}",
            f"path: {self.folder_path}",
            f"total: {self.total_count}",
            f"success: {self.success_count}",
            f"failed: {self.failed_count}",
            f"elapsed: {elapsed:.1f}s",
        ]
        for v in self.videos:
            if not v.success:
                lines.append(f"  - {v.bvid}: {v.error}")
        return "\n".join(lines)


class SearchService:
    """Bulk video download + transcription, used by AI function-call tools."""

    def __init__(
        self,
        *,
        data_dir: str | Path,
        http_client: BilibiliHTTPClient,
        pipeline: TranscriptPipeline,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._http = http_client
        self._pipeline = pipeline
        self._search_dir = self._data_dir / "search_results"
        self._search_dir.mkdir(parents=True, exist_ok=True)

    async def process_bv_list(
        self,
        *,
        bv_list: list[str],
        folder_name: str,
        max_concurrent: int = 1,
        prefer_subtitle: bool = True,
        quality: str = "fast",
        subtitle_langs: tuple[str, ...] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> BatchResult:
        task_id = str(int(time.time() * 1000))
        safe_name = _SAFE_NAME_RE.sub("_", folder_name)[:30]
        folder_path = self._search_dir / f"{task_id}_{safe_name}"
        folder_path.mkdir(parents=True, exist_ok=True)

        result = BatchResult(
            folder_name=folder_name,
            folder_path=folder_path,
            total_count=len(bv_list),
            started_at=time.time(),
        )

        semaphore = asyncio.Semaphore(max(1, max_concurrent))
        completed = 0
        lock = asyncio.Lock()

        async def _process(bvid: str) -> None:
            nonlocal completed
            try:
                async with semaphore:
                    video_result = await self._process_one(
                        bvid, folder_path, prefer_subtitle, quality, subtitle_langs
                    )
            except Exception as exc:
                logger.warning(f"unexpected search processing failure for {bvid}: {exc}", exc_info=True)
                video_result = VideoTranscriptResult(
                    bvid=bvid,
                    success=False,
                    error=f"unexpected failure: {exc}",
                )

            async with lock:
                completed += 1
                if video_result.success:
                    result.success_count += 1
                else:
                    result.failed_count += 1
                result.videos.append(video_result)
                if progress_callback is not None:
                    try:
                        await progress_callback(
                            {
                                "completed": completed,
                                "total": result.total_count,
                                "title": video_result.info.title if video_result.info else bvid,
                                "success": video_result.success,
                                "error": video_result.error,
                                "is_last": completed == result.total_count,
                                "success_count": result.success_count,
                                "failed_count": result.failed_count,
                            }
                        )
                    except Exception as exc:
                        logger.warning(f"progress_callback raised: {exc}")

        await asyncio.gather(*(_process(bvid) for bvid in bv_list), return_exceptions=True)
        result.finished_at = time.time()
        try:
            (folder_path / "_summary.txt").write_text(result.to_summary(), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"summary file write failed: {exc}")
        return result

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    async def _process_one(
        self,
        bvid: str,
        folder_path: Path,
        prefer_subtitle: bool,
        quality: str,
        subtitle_langs: tuple[str, ...] | None = None,
    ) -> VideoTranscriptResult:
        result = VideoTranscriptResult(bvid=bvid)
        try:
            info = await get_video_info(self._http, bvid)
        except BiliVideoError as exc:
            result.error = f"info lookup failed: {exc}"
            return result
        result.info = info
        url = info.url

        try:
            output = await self._pipeline.fetch(
                url,
                prefer_subtitle=prefer_subtitle,
                quality=quality,
                subtitle_langs=subtitle_langs,
            )
        except BiliVideoError as exc:
            result.error = exc.user_message
            return result
        finally:
            pass  # cleanup via TranscriptPipeline

        # Always cleanup audio after we use it
        self._pipeline.cleanup_audio(output.audio)

        result.transcript = _format_transcript(output.transcript)
        result.success = True
        self._save_to_file(info, result.transcript, folder_path)
        return result

    @staticmethod
    def _save_to_file(info: VideoInfo, transcript_text: str, folder_path: Path) -> None:
        safe_title = _SAFE_NAME_RE.sub("_", info.title)[:50]
        file_path = folder_path / f"{info.bvid}_{safe_title}.txt"
        body = (
            "=" * 50 + "\n"
            "视频信息\n"
            + "=" * 50 + "\n"
            f"标题: {info.title}\n"
            f"UP主: {info.owner_name}\n"
            f"BV号: {info.bvid}\n"
            f"播放量: {format_count(info.view)}\n"
            f"弹幕: {format_count(info.danmaku)}\n"
            f"点赞: {format_count(info.like)}\n"
            f"链接: {info.url}\n"
            "\n" + "=" * 50 + "\n"
            "转写内容\n"
            + "=" * 50 + "\n\n"
            f"{transcript_text}\n"
        )
        try:
            file_path.write_text(body, encoding="utf-8")
        except OSError as exc:
            logger.warning(f"transcript save failed: {exc}")


def _format_transcript(transcript: TranscriptResult) -> str:
    return "\n".join(
        f"[{int(seg.start // 60):02d}:{int(seg.start % 60):02d}] {seg.text}"
        for seg in transcript.segments
    )
