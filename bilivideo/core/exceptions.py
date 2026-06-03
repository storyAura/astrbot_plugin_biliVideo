"""Structured exception hierarchy.

Replaces the substring-matching style of `_format_user_error` from the
previous implementation. Each exception carries its own user-facing message,
so handlers can surface a friendly description without parsing strings.
"""

from __future__ import annotations

from pathlib import Path


class BiliVideoError(Exception):
    """Base class for all plugin-specific errors.

    `user_message` is what we surface to chat. Falls back to the standard
    string representation when not provided.
    """

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class NetworkError(BiliVideoError):
    """Generic network failure (DNS, timeout, connection reset, etc.)."""

    def __init__(self, message: str = "网络请求失败") -> None:
        super().__init__(message, user_message="❌ 网络连接失败,请检查网络后重试")


class BilibiliAPIError(BiliVideoError):
    """B 站接口返回了非 0 的 code。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"Bilibili API code={code}: {message}")
        self.code = code
        self.api_message = message
        self.user_message = f"❌ B 站接口返回错误 ({code}):{message}"


class RiskControlError(BiliVideoError):
    """B 站触发了风控(412/-352)。通常需要更换 cookie 或更换 IP。"""

    def __init__(self, message: str = "B 站风控拦截") -> None:
        super().__init__(
            message,
            user_message="❌ B 站触发风控,可能需要重新 /B站登录 或稍后重试",
        )


class RateLimitError(BiliVideoError):
    """LLM provider 返回 429。"""

    def __init__(self, retry_after: float | None = None) -> None:
        msg = "LLM rate limited"
        if retry_after is not None:
            msg = f"LLM rate limited (retry after {retry_after:.1f}s)"
        super().__init__(msg, user_message="⏳ AI 服务限流,请稍后重试")
        self.retry_after = retry_after


class NotLoggedInError(BiliVideoError):
    """需要登录才能完成该操作。"""

    def __init__(self) -> None:
        super().__init__("Bilibili not logged in", user_message="❌ 请先发送 /B站登录 完成扫码登录")


class DownloadError(BiliVideoError):
    """音频/视频下载失败。"""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(
            message,
            user_message=user_message or "❌ 视频音频下载失败,可能是版权限制或视频已删除",
        )


class TranscriptionError(BiliVideoError):
    """字幕获取或 ASR 转写失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            user_message="❌ 视频转写失败,请稍后重试或尝试其他视频",
        )


class LLMError(BiliVideoError):
    """LLM 调用失败。"""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(
            message,
            user_message=user_message or "❌ AI 服务暂时不可用,请稍后重试",
        )


class RenderError(BiliVideoError):
    """图片渲染失败,通常需要回退到纯文本。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, user_message="❌ 图片渲染失败,已回退为纯文本")


class PartialRenderError(RenderError):
    """Some pages rendered, but at least one page failed."""

    def __init__(
        self,
        message: str,
        *,
        generated_paths: list[Path] | None = None,
        failed_pages: list[int] | None = None,
        page_errors: dict[int, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.generated_paths = generated_paths or []
        self.failed_pages = failed_pages or []
        self.page_errors = page_errors or {}


class CooldownError(BiliVideoError):
    """用户在冷却中。"""

    def __init__(self, remaining: int) -> None:
        super().__init__(
            f"cooldown {remaining}s",
            user_message=f"⏳ 操作太频繁,请等 {remaining} 秒后再试",
        )
        self.remaining = remaining


class AccessDeniedError(BiliVideoError):
    """群聊访问控制不通过。"""

    def __init__(self) -> None:
        super().__init__("access denied", user_message="⛔ 你没有权限使用此插件")
