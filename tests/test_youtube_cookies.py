"""YouTube cookie selection + bot-check error mapping for the downloader."""

from __future__ import annotations

from pathlib import Path

from bilivideo.auth.youtube_cookies import (
    YouTubeCookieStore,
    count_cookies,
    normalize_youtube_cookies,
)
from bilivideo.core.exceptions import DownloadError
from bilivideo.downloader.ytdlp_downloader import YtDlpDownloader, _wrap_download_error


def test_download_error_accepts_custom_user_message() -> None:
    err = DownloadError("boom", user_message="custom")
    assert err.user_message == "custom"
    assert str(err) == "boom"
    # default preserved when user_message omitted
    assert "下载失败" in DownloadError("boom").user_message


def test_wrap_download_error_youtube_bot_check() -> None:
    exc = Exception("ERROR: [youtube] xxx: Sign in to confirm you're not a bot")
    wrapped = _wrap_download_error(exc, "https://www.youtube.com/watch?v=xxx")
    assert isinstance(wrapped, DownloadError)
    assert "/YT登录" in wrapped.user_message
    assert "小号" in wrapped.user_message


def test_wrap_download_error_youtube_other_failure_is_generic() -> None:
    exc = Exception("ERROR: Video unavailable")
    wrapped = _wrap_download_error(exc, "https://youtu.be/xxx")
    assert "下载失败" in wrapped.user_message  # generic copyright/deleted hint


def test_wrap_download_error_non_youtube_keeps_generic() -> None:
    # bot-check signature present, but URL is bilibili -> stay generic
    exc = Exception("Sign in to confirm you're not a bot")
    wrapped = _wrap_download_error(exc, "https://www.bilibili.com/video/BV1xx411c7mD")
    assert "下载失败" in wrapped.user_message


def test_cookiefile_for_youtube_prefers_youtube_jar(tmp_path: Path) -> None:
    yt_cookie = tmp_path / "youtube_cookies.txt"
    yt_cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    dl = YtDlpDownloader(data_dir=tmp_path / "audio", youtube_cookies_file=yt_cookie)
    assert dl._cookiefile_for("https://www.youtube.com/watch?v=abc") == str(yt_cookie)
    # bilibili URL has no bili cookies configured -> None
    assert dl._cookiefile_for("https://www.bilibili.com/video/BV1xx411c7mD") is None


def test_cookiefile_for_youtube_missing_file_returns_none(tmp_path: Path) -> None:
    missing = tmp_path / "nope.txt"
    dl = YtDlpDownloader(data_dir=tmp_path / "audio", youtube_cookies_file=missing)
    assert dl._cookiefile_for("https://youtu.be/abc") is None


def test_cookiefile_for_bilibili_uses_bili_cookies(tmp_path: Path) -> None:
    dl = YtDlpDownloader(
        data_dir=tmp_path / "audio",
        cookies={"SESSDATA": "x", "buvid3": "y"},
    )
    cookiefile = dl._cookiefile_for("https://www.bilibili.com/video/BV1xx411c7mD")
    assert cookiefile is not None and cookiefile.endswith("cookies.txt")
    # youtube with no jar configured -> None
    assert dl._cookiefile_for("https://youtu.be/abc") is None


def test_normalize_header_to_netscape() -> None:
    out = normalize_youtube_cookies("SID=abc; HSID=def")
    assert out is not None
    assert out.startswith("# Netscape")
    assert ".youtube.com" in out
    assert "SID\tabc" in out
    assert count_cookies(out) == 2


def test_normalize_netscape_passthrough_keeps_httponly() -> None:
    raw = (
        "# Netscape HTTP Cookie File\n"
        "# a comment\n"
        ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\t__Secure-1PSID\txyz\n"
    )
    out = normalize_youtube_cookies(raw)
    assert out is not None
    assert "SID\tabc" in out
    assert "#HttpOnly_.youtube.com\tTRUE" in out  # httpOnly data line preserved
    assert "# a comment" not in out  # plain comments dropped
    assert count_cookies(out) == 2


def test_normalize_garbage_returns_none() -> None:
    assert normalize_youtube_cookies("hello world") is None
    assert normalize_youtube_cookies("   ") is None
    assert normalize_youtube_cookies("") is None


def test_store_save_has_clear(tmp_path: Path) -> None:
    store = YouTubeCookieStore(tmp_path)
    assert store.has() is False
    assert store.save("SID=abc; HSID=def") == 2
    assert store.has() is True
    assert Path(store.path).exists()
    assert store.clear() is True
    assert store.has() is False


def test_store_rejects_non_cookie_paste(tmp_path: Path) -> None:
    store = YouTubeCookieStore(tmp_path)
    assert store.save("not a cookie") is None
    assert store.has() is False
