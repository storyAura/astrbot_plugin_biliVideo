import os
import json
import re
from typing import Optional, List

import yt_dlp

from astrbot.api import logger
from .base import Downloader, QUALITY_MAP
from ..models.audio_model import AudioDownloadResult
from ..models.transcriber_model import TranscriptResult, TranscriptSegment


class BilibiliDownloader(Downloader):
    def __init__(self, data_dir: str, cookies: Optional[dict] = None):
        super().__init__()
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        # 从 cookie dict 生成 yt-dlp 可用的 cookies.txt (Netscape 格式)
        self.cookies_file = None
        if cookies and any(cookies.values()):
            self.cookies_file = os.path.join(self.data_dir, "cookies.txt")
            self._write_cookies_file(cookies)

    def _write_cookies_file(self, cookies: dict):
        """从 cookie dict 生成 Netscape 格式 cookies.txt"""
        lines = ["# Netscape HTTP Cookie File"]
        for name, value in cookies.items():
            if value:
                lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
        with open(self.cookies_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")


    def download(
        self,
        video_url: str,
        output_dir: Optional[str] = None,
        quality: str = "fast",
    ) -> AudioDownloadResult:
        """下载B站视频的音频"""
        if output_dir is None:
            output_dir = self.data_dir
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': QUALITY_MAP.get(quality, '64'),
                }
            ],
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

        if self.cookies_file and os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            audio_path = os.path.join(output_dir, f"{video_id}.mp3")

        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="bilibili",
            video_id=video_id,
            raw_info=info,
        )

    def download_subtitles(self, video_url: str, output_dir: Optional[str] = None,
                           langs: Optional[List[str]] = None) -> Optional[TranscriptResult]:
        """尝试获取B站视频字幕"""
        if output_dir is None:
            output_dir = self.data_dir
        os.makedirs(output_dir, exist_ok=True)

        if langs is None:
            langs = ['zh-Hans', 'zh', 'zh-CN', 'ai-zh', 'en', 'en-US']

        video_id = self._extract_video_id(video_url)

        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': langs,
            'subtitlesformat': 'srt/json3/best',
            'skip_download': True,
            'outtmpl': os.path.join(output_dir, f'{video_id}.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }

        if self.cookies_file and os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)

                subtitles = info.get('requested_subtitles') or {}
                if not subtitles:
                    logger.info(f"B站视频 {video_id} 没有可用字幕")
                    return None

                detected_lang = None
                sub_info = None
                for lang in langs:
                    if lang in subtitles:
                        detected_lang = lang
                        sub_info = subtitles[lang]
                        break

                if not detected_lang:
                    for lang, info_item in subtitles.items():
                        if lang != 'danmaku':
                            detected_lang = lang
                            sub_info = info_item
                            break

                if not sub_info:
                    return None

                if 'data' in sub_info and sub_info['data']:
                    return self._parse_srt_content(sub_info['data'], detected_lang)

                ext = sub_info.get('ext', 'srt')
                subtitle_file = os.path.join(output_dir, f"{video_id}.{detected_lang}.{ext}")

                if not os.path.exists(subtitle_file):
                    return None

                if ext == 'json3':
                    return self._parse_json3_subtitle(subtitle_file, detected_lang)
                else:
                    with open(subtitle_file, 'r', encoding='utf-8') as f:
                        return self._parse_srt_content(f.read(), detected_lang)

        except Exception as e:
            logger.warning(f"获取B站字幕失败: {e}")
            return None

    def _extract_video_id(self, url: str) -> Optional[str]:
        """从B站链接提取视频ID"""
        match = re.search(r"BV([0-9A-Za-z]+)", url)
        return f"BV{match.group(1)}" if match else None

    def _parse_srt_content(self, srt_content: str, language: str) -> Optional[TranscriptResult]:
        """解析 SRT 格式字幕"""
        try:
            segments = []
            pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n\d+\n|$)'
            matches = re.findall(pattern, srt_content, re.DOTALL)

            for match in matches:
                idx, start_time, end_time, text = match
                text = text.strip()
                if not text:
                    continue

                def time_to_seconds(t):
                    parts = t.replace(',', '.').split(':')
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

                segments.append(TranscriptSegment(
                    start=time_to_seconds(start_time),
                    end=time_to_seconds(end_time),
                    text=text
                ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'format': 'srt'}
            )
        except Exception as e:
            logger.warning(f"解析SRT字幕失败: {e}")
            return None

    def _parse_json3_subtitle(self, subtitle_file: str, language: str) -> Optional[TranscriptResult]:
        """解析 json3 格式字幕"""
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            segments = []
            events = data.get('events', [])

            for event in events:
                start_ms = event.get('tStartMs', 0)
                duration_ms = event.get('dDurationMs', 0)
                segs = event.get('segs', [])
                text = ''.join(seg.get('utf8', '') for seg in segs).strip()

                if text:
                    segments.append(TranscriptSegment(
                        start=start_ms / 1000.0,
                        end=(start_ms + duration_ms) / 1000.0,
                        text=text
                    ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'file': subtitle_file}
            )
        except Exception as e:
            logger.warning(f"解析字幕文件失败: {e}")
            return None
