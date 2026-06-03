"""Renderer partial-failure tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bilivideo.core.exceptions import PartialRenderError, RenderError
from bilivideo.render.pillow_renderer import PillowRenderer
from bilivideo.render.wkhtml_renderer import WkHtmlRenderer


def _long_doc() -> str:
    parts = ["# 标题"]
    for idx in range(3):
        parts.append(f"## 章节{idx}")
        parts.append("内容" * 20)
    return "\n".join(parts)


def test_wkhtml_renderer_partial_keeps_successful_pages(tmp_path, monkeypatch) -> None:
    renderer = WkHtmlRenderer(output_dir=tmp_path)

    def _render_page(markdown_text, destination: Path, **kwargs):
        if destination.name.endswith("_p1.png"):
            raise RenderError("page1")
        destination.write_bytes(b"ok")

    monkeypatch.setattr(renderer, "_render_html_to_png", _render_page)

    with pytest.raises(PartialRenderError) as exc:
        renderer.render(_long_doc(), base_filename="note", max_cards_per_image=1, enable_split=True)

    assert exc.value.failed_pages == [1]
    assert [path.name for path in exc.value.generated_paths] == ["note_p2.png", "note_p3.png"]


def test_pillow_renderer_partial_keeps_successful_pages(tmp_path, monkeypatch) -> None:
    renderer = PillowRenderer(output_dir=tmp_path)

    def _render_one(markdown_text, base_filename: str, **kwargs):
        if base_filename.endswith("_p1"):
            raise RenderError("page1")
        out = Path(tmp_path) / f"{base_filename}.png"
        out.write_bytes(b"ok")
        return [out]

    monkeypatch.setattr(renderer, "_render_one", _render_one)

    with pytest.raises(PartialRenderError) as exc:
        renderer.render(_long_doc(), base_filename="note", max_cards_per_image=1, enable_split=True)

    assert exc.value.failed_pages == [1]
    assert [path.name for path in exc.value.generated_paths] == ["note_p2.png", "note_p3.png"]
