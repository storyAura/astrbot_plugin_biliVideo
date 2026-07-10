"""bilivideo - AstrBot Bilibili 视频解析与 AI 总结的实现层。

本子套件持有所有非框架性的实现:配置、API 客户端、解析、总结、渲染、
订阅推送、命令处理器等。`main.py` 仅负责 Star 注册与 handler 委派。
"""

from pathlib import Path

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


def _load_version() -> str:
    """metadata.yaml 是版本号的唯一来源;这里解析它,避免多处硬编码漂移。"""

    meta = Path(__file__).resolve().parent.parent / "metadata.yaml"
    try:
        for line in meta.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "version":
                return value.strip().lstrip("vV")
    except OSError:
        pass
    return "0.0.0"


__version__ = _load_version()
