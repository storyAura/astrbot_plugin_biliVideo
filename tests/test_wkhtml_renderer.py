"""Contract tests for the restored wkhtmltoimage renderer."""

from __future__ import annotations

from pathlib import Path

import imgkit

from bilivideo.render.wkhtml_renderer import WkHtmlRenderer


def test_wkhtml_renderer_uses_original_html_pipeline(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _from_string(html: str, destination: str, *, options: dict) -> None:
        captured.update(html=html, destination=destination, options=options)
        Path(destination).write_bytes(b"x" * 2048)

    monkeypatch.setattr(imgkit, "from_string", _from_string)
    renderer = WkHtmlRenderer(output_dir=tmp_path, image_width=900)

    outputs = renderer.render(
        "# 视频标题\n\n## 章节\n- **重点内容**",
        base_filename="summary",
        enable_split=False,
    )

    assert outputs == [tmp_path / "summary.png"]
    html = str(captured["html"])
    assert '<div class="header"><h1>视频标题</h1>' in html
    assert '<div class="card card-0"' in html
    assert "<strong>重点内容</strong>" in html
    assert captured["destination"] == str(tmp_path / "summary.png")
    assert captured["options"] == {
        "format": "png",
        "width": "900",
        "encoding": "UTF-8",
        "quality": "94",
        "disable-javascript": "",
        "disable-local-file-access": "",
        "no-stop-slow-scripts": "",
        "disable-smart-width": "",
    }
