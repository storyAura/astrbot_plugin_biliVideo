"""Core domain primitives: config, types, constants, errors, logging."""

from .config import PluginConfig
from .constants import (
    BILI_DOMAINS,
    BV_REGEX,
    DEFAULT_USER_AGENT,
    LONG_URL_REGEX,
    SHORT_URL_REGEX,
)
from .exceptions import (
    BiliVideoError,
    LLMError,
    NetworkError,
    NotLoggedInError,
    RenderError,
    TranscriptionError,
)
from .logging import get_logger

__all__ = [
    "BILI_DOMAINS",
    "BV_REGEX",
    "DEFAULT_USER_AGENT",
    "LONG_URL_REGEX",
    "SHORT_URL_REGEX",
    "BiliVideoError",
    "LLMError",
    "NetworkError",
    "NotLoggedInError",
    "PluginConfig",
    "RenderError",
    "TranscriptionError",
    "get_logger",
]
