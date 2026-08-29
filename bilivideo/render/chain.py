"""Select the legacy HTML renderer or the all-Python fallback."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..core.exceptions import RenderError
from ..core.logging import get_logger
from .pillow_renderer import PillowRenderer, check_pillow_ready
from .wkhtml_renderer import WkHtmlRenderer

logger = get_logger("BiliVideo/Render")


def _wkhtmltoimage_path() -> str | None:
    return shutil.which("wkhtmltoimage") or shutil.which("wkhtmltoimage.exe")


class RenderChain:
    """Use wkhtmltoimage when installed; otherwise use the Python renderer."""

    def __init__(self, *, output_dir: str | Path, image_width: int = 900) -> None:
        self._renderer: WkHtmlRenderer | PillowRenderer | None = None
        self._backend_name: str | None = None
        self._diagnostics: dict[str, str] = {}

        wkhtml_path = _wkhtmltoimage_path()
        if wkhtml_path:
            self._renderer = WkHtmlRenderer(output_dir=output_dir, image_width=image_width)
            self._backend_name = "wkhtmltopdf"
            self._diagnostics["wkhtmltopdf"] = f"ready ({wkhtml_path})"
            self._diagnostics["python"] = "standby: wkhtmltopdf selected"
            return

        self._diagnostics["wkhtmltopdf"] = "missing wkhtmltoimage on PATH"
        logger.warning("wkhtmltoimage not found on PATH; using the Python image renderer")

        ready, reason = check_pillow_ready()
        self._diagnostics["python"] = ("ready " if ready else "unavailable: ") + reason
        if ready:
            self._renderer = PillowRenderer(output_dir=output_dir, image_width=image_width)
            self._backend_name = "python"
        else:
            logger.warning(f"Python image renderer unavailable: {reason}")

    def render(
        self,
        markdown_text: str,
        *,
        base_filename: str,
        max_cards_per_image: int = 6,
        enable_split: bool = True,
    ) -> list[Path]:
        if self._renderer is None:
            raise RenderError("no image renderer available")
        return self._renderer.render(
            markdown_text,
            base_filename=base_filename,
            max_cards_per_image=max_cards_per_image,
            enable_split=enable_split,
        )

    @property
    def available_backends(self) -> list[str]:
        return [self._backend_name] if self._backend_name is not None else []

    @property
    def backend_diagnostics(self) -> dict[str, str]:
        return dict(self._diagnostics)
