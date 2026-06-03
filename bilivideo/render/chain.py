"""Renderer chain: pick the first backend that's actually available.

Design philosophy: never crash if image rendering can't happen — always
fall through to the next backend, finally giving up to plain text in the
caller layer (`_render_helper.render_note_components`).

Selection order:
  1. **wkhtmltopdf** via imgkit — only if `wkhtmltoimage` resolves on PATH.
  2. **Pillow** via `PillowRenderer` — runs anywhere Pillow is installed
     and a CJK font exists. Visually plainer but production-safe.
  3. **None** → caller returns the Markdown as plain text.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from ..core.exceptions import PartialRenderError, RenderError
from ..core.logging import get_logger
from .pillow_renderer import PillowRenderer, check_pillow_ready
from .wkhtml_renderer import WkHtmlRenderer

logger = get_logger("BiliVideo/RenderChain")


class _Renderer(Protocol):
    def render(
        self,
        markdown_text: str,
        *,
        base_filename: str,
        max_cards_per_image: int = 6,
        enable_split: bool = True,
    ) -> list[Path]: ...


def _wkhtmltoimage_path() -> str | None:
    return shutil.which("wkhtmltoimage") or shutil.which("wkhtmltoimage.exe")


class RenderChain:
    """Try each available backend until one produces output."""

    def __init__(self, *, output_dir: str | Path, image_width: int = 1400) -> None:
        self._backends: list[tuple[str, _Renderer]] = []
        self._diagnostics: dict[str, str] = {}

        wkhtml_path = _wkhtmltoimage_path()
        if wkhtml_path:
            self._backends.append(
                ("wkhtmltopdf", WkHtmlRenderer(output_dir=output_dir, image_width=image_width))
            )
            self._diagnostics["wkhtmltopdf"] = f"ready ({wkhtml_path})"
        else:
            self._diagnostics["wkhtmltopdf"] = "missing wkhtmltoimage on PATH"
            logger.warning(
                "wkhtmltoimage not found on PATH; skipping high-fidelity HTML renderer"
            )

        pillow_ready, pillow_reason = check_pillow_ready()
        self._diagnostics["pillow"] = ("ready " if pillow_ready else "unavailable: ") + pillow_reason
        if pillow_ready:
            self._backends.append(
                ("pillow", PillowRenderer(output_dir=output_dir, image_width=image_width))
            )
        else:
            logger.warning(f"Pillow renderer unavailable: {pillow_reason}")

        if not self._backends:
            logger.warning("no image renderer backends available; image mode will fall back to text")

    def render(
        self,
        markdown_text: str,
        *,
        base_filename: str,
        max_cards_per_image: int = 6,
        enable_split: bool = True,
    ) -> list[Path]:
        last_error: Exception | None = None
        partial: PartialRenderError | None = None
        for name, backend in self._backends:
            try:
                paths = backend.render(
                    markdown_text,
                    base_filename=base_filename,
                    max_cards_per_image=max_cards_per_image,
                    enable_split=enable_split,
                )
                logger.debug(f"renderer '{name}' produced {len(paths)} images")
                if partial is not None:
                    logger.warning(
                        f"discarding partial outputs from an earlier backend because "
                        f"renderer '{name}' completed successfully"
                    )
                return paths
            except PartialRenderError as exc:
                logger.warning(
                    f"renderer '{name}' partially failed: {exc}; keeping successful pages "
                    "and trying next backend for a complete render"
                )
                if partial is None or len(exc.generated_paths) > len(partial.generated_paths):
                    partial = exc
                last_error = exc
                continue
            except RenderError as exc:
                logger.warning(f"renderer '{name}' failed: {exc}; trying next backend")
                last_error = exc
                continue
            except Exception as exc:
                logger.warning(f"renderer '{name}' raised unexpectedly: {exc}; trying next backend")
                last_error = exc
                continue
        if partial is not None and partial.generated_paths:
            raise partial
        raise RenderError(
            f"all image backends failed; last error: {last_error}" if last_error else "no backends available"
        )

    @property
    def available_backends(self) -> list[str]:
        return [name for name, _ in self._backends]

    @property
    def backend_diagnostics(self) -> dict[str, str]:
        return dict(self._diagnostics)
