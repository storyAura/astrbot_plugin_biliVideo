"""Audio downloader & subtitle harvester via yt-dlp.

Refactored from the previous `BilibiliDownloader`:
  * subtitle parsing extracted into helpers so it can be reused/tested
  * cookie file lifecycle isolated; we always overwrite to keep it in sync
  * uses dataclasses from `core.types`
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Iterable, Mapping
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import yt_dlp

from ..core.constants import QUALITY_TO_KBPS, YTDLP_SOCKET_TIMEOUT_SECONDS
from ..core.exceptions import DownloadError, TranscriptionError
from ..core.logging import get_logger
from ..core.types import AudioDownloadResult, TranscriptResult, TranscriptSegment
from ..parsing.url_extractor import detect_platform

logger = get_logger("BiliVideo/Download")


@lru_cache(maxsize=1)
def _ffmpeg_location() -> str | None:
    """Resolve an ffmpeg binary for yt-dlp's audio postprocessor.

    Prefer a system ffmpeg (respect the host/container setup); when none is
    on PATH, fall back to the static binary shipped by ``imageio-ffmpeg`` so
    audio extraction works on a bare VPS with no ``apt install ffmpeg``.
    Returns ``None`` to let yt-dlp search PATH itself.
    """

    if shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"):
        return None
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - optional wheel
        logger.warning(f"imageio-ffmpeg unavailable; relying on PATH ffmpeg: {exc}")
        return None


DEFAULT_SUBTITLE_LANGS: tuple[str, ...] = (
    "zh-Hans",
    "zh",
    "zh-CN",
    "ai-zh",
    "en",
    "en-US",
)


class YtDlpDownloader:
    """Bilibili audio + subtitle downloader."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        cookies: Mapping[str, str] | None = None,
        youtube_cookies_file: str | Path | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cookies_file: Path | None = None
        self._youtube_cookies_file: Path | None = (
            Path(youtube_cookies_file) if youtube_cookies_file else None
        )
        self.update_cookies(cookies)

    # ------------------------------------------------------------------
    # cookie helpers
    # ------------------------------------------------------------------
    def update_cookies(self, cookies: Mapping[str, str] | None) -> None:
        if not cookies:
            path = self._data_dir / "cookies.txt"
            if path.exists():
                try:
                    path.unlink()
                    logger.debug(f"downloader_cookiefile_removed path={path}")
                except OSError as exc:
                    logger.warning(f"cookies.txt removal failed: {exc}")
            self._cookies_file = None
            return
        path = self._data_dir / "cookies.txt"
        lines = ["# Netscape HTTP Cookie File"]
        for name, value in cookies.items():
            if value:
                lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
        try:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
            logger.debug(f"downloader_cookiefile_written path={path} keys={list(cookies.keys())}")
        except OSError as exc:
            logger.warning(f"cookies.txt write failed: {exc}")
            self._cookies_file = None
            return
        self._cookies_file = path

    def _cookiefile_for(self, video_url: str) -> str | None:
        """Pick the cookie jar for the target platform.

        YouTube increasingly blocks datacenter IPs with a "confirm you're not
        a bot" check; an admin-supplied cookies.txt (exported from a burner
        Google account) is the documented workaround. Bilibili keeps using the
        login cookies written by ``update_cookies``.
        """

        if detect_platform(video_url) == "youtube":
            if self._youtube_cookies_file and self._youtube_cookies_file.exists():
                return str(self._youtube_cookies_file)
            return None
        if self._cookies_file and self._cookies_file.exists():
            return str(self._cookies_file)
        return None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def download_audio(
        self,
        video_url: str,
        *,
        output_dir: str | Path | None = None,
        quality: str = "fast",
    ) -> AudioDownloadResult:
        target = Path(output_dir) if output_dir else self._data_dir
        target.mkdir(parents=True, exist_ok=True)

        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(target / "%(id)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": QUALITY_TO_KBPS.get(quality, "64"),
                }
            ],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": YTDLP_SOCKET_TIMEOUT_SECONDS,
        }
        cookiefile = self._cookiefile_for(video_url)
        if cookiefile:
            opts["cookiefile"] = cookiefile

        ffmpeg_path = _ffmpeg_location()
        if ffmpeg_path:
            opts["ffmpeg_location"] = ffmpeg_path

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            raise _wrap_download_error(exc, video_url) from exc

        video_id = info.get("id", "")
        audio_path = target / f"{video_id}.mp3"
        return AudioDownloadResult(
            file_path=str(audio_path),
            title=str(info.get("title", "")),
            duration=float(info.get("duration", 0) or 0),
            cover_url=info.get("thumbnail"),
            platform=str(info.get("extractor_key") or info.get("extractor") or "bilibili").lower(),
            video_id=str(video_id),
            raw_info=dict(info),
        )

    def download_subtitles(
        self,
        video_url: str,
        *,
        output_dir: str | Path | None = None,
        langs: Iterable[str] | None = None,
    ) -> TranscriptResult | None:
        target = Path(output_dir) if output_dir else self._data_dir
        target.mkdir(parents=True, exist_ok=True)
        lang_list = list(langs) if langs else list(DEFAULT_SUBTITLE_LANGS)
        video_id = _extract_video_id_from_url(video_url) or _stable_video_id(video_url)

        opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": lang_list,
            "subtitlesformat": "srt/json3/best",
            "skip_download": True,
            "outtmpl": str(target / f"{video_id}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": YTDLP_SOCKET_TIMEOUT_SECONDS,
        }
        cookiefile = self._cookiefile_for(video_url)
        if cookiefile:
            opts["cookiefile"] = cookiefile

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            logger.warning(f"subtitle download failed: {exc}")
            return None

        subtitles = info.get("requested_subtitles") or {}
        if not subtitles:
            logger.info(f"{video_id}: no platform subtitles")
            return None

        for lang in lang_list:
            if lang in subtitles:
                return _parse_sub(subtitles[lang], lang, target, video_id)
        # any other available language except 'danmaku'
        for lang, sub_info in subtitles.items():
            if lang == "danmaku":
                continue
            return _parse_sub(sub_info, lang, target, video_id)
        return None


# ──────────────────────────── helpers ──────────────────────────────


_YT_BOT_CHECK_SIGNS: tuple[str, ...] = (
    "sign in to confirm",
    "confirm you're not a bot",
    "confirm you are not a bot",
)


def _wrap_download_error(exc: Exception, video_url: str) -> DownloadError:
    """Map a yt-dlp download failure to a DownloadError with a useful hint.

    YouTube on a datacenter IP often refuses with a "confirm you're not a bot"
    sign-in wall. Surface a message that points at /YT登录 and the burner-account
    workaround instead of the generic copyright/deleted hint.
    """

    message = str(exc)
    if detect_platform(video_url) == "youtube" and any(
        sign in message.lower() for sign in _YT_BOT_CHECK_SIGNS
    ):
        return DownloadError(
            message,
            user_message=(
                "❌ YouTube 拒绝下载:需要登录验证(VPS 机房 IP 常被要求\"确认你不是机器人\")。\n"
                "请发送 /YT登录 查看如何提供 cookies。\n"
                "⚠️ 强烈建议使用小号/不重要的 Google 账号,有封号风险!"
            ),
        )
    return DownloadError(message)


def _extract_video_id_from_url(url: str) -> str | None:
    match = re.search(r"BV[0-9A-Za-z]{10}", url or "")
    return match.group(0) if match else None


def _stable_video_id(url: str) -> str:
    return "video_" + sha256((url or "").encode("utf-8")).hexdigest()[:12]


def _parse_sub(sub_info: dict, language: str, output_dir: Path, video_id: str) -> TranscriptResult | None:
    inline = sub_info.get("data")
    if isinstance(inline, str) and inline:
        return _parse_srt(inline, language)
    ext = sub_info.get("ext", "srt")
    path = output_dir / f"{video_id}.{language}.{ext}"
    if not path.exists():
        return None
    if ext == "json3":
        return _parse_json3(path, language)
    try:
        return _parse_srt(path.read_text(encoding="utf-8"), language)
    except OSError as exc:
        raise TranscriptionError(f"subtitle file read error: {exc}") from exc


def _parse_srt(content: str, language: str) -> TranscriptResult | None:
    pattern = re.compile(
        r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n\d+\n|$)",
        re.DOTALL,
    )
    segments: list[TranscriptSegment] = []
    for _, start_t, end_t, text in pattern.findall(content):
        text = text.strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=_srt_time(start_t),
                end=_srt_time(end_t),
                text=text,
            )
        )
    if not segments:
        return None
    full_text = " ".join(seg.text for seg in segments)
    return TranscriptResult(
        language=language,
        full_text=full_text,
        segments=tuple(segments),
        raw={"source": "bilibili_subtitle", "format": "srt"},
    )


def _parse_json3(path: Path, language: str) -> TranscriptResult | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"json3 subtitle parse failed: {exc}")
        return None

    segments: list[TranscriptSegment] = []
    for event in data.get("events", []):
        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)
        text = "".join(s.get("utf8", "") for s in event.get("segs", [])).strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=start_ms / 1000.0,
                end=(start_ms + duration_ms) / 1000.0,
                text=text,
            )
        )
    if not segments:
        return None
    return TranscriptResult(
        language=language,
        full_text=" ".join(seg.text for seg in segments),
        segments=tuple(segments),
        raw={"source": "bilibili_subtitle", "format": "json3"},
    )


def _srt_time(token: str) -> float:
    parts = token.replace(",", ".").split(":")
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
