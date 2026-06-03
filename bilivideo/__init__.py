"""bilivideo - AstrBot Bilibili 视频解析与 AI 总结的实现层。

本子套件持有所有非框架性的实现:配置、API 客户端、解析、总结、渲染、
订阅推送、命令处理器等。`main.py` 仅负责 Star 注册与 handler 委派。
"""

from .core.config import PluginConfig
from .core.exceptions import (
    BiliVideoError,
    LLMError,
    NetworkError,
    NotLoggedInError,
    RenderError,
    TranscriptionError,
)

__all__ = [
    "BiliVideoError",
    "LLMError",
    "NetworkError",
    "NotLoggedInError",
    "PluginConfig",
    "RenderError",
    "TranscriptionError",
]

__version__ = "2.0.0"
