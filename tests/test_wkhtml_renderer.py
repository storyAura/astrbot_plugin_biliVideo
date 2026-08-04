"""Contract tests for the restored wkhtmltoimage renderer."""

from __future__ import annotations

from pathlib import Path

import imgkit

from bilivideo.render.wkhtml_renderer import WkHtmlRenderer, _markdown_to_html


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


def test_wkhtml_renderer_embeds_inline_and_display_math(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _from_string(html: str, destination: str, *, options: dict) -> None:
        captured.update(html=html, options=options)
        Path(destination).write_bytes(b"x" * 2048)

    monkeypatch.setattr(imgkit, "from_string", _from_string)
    renderer = WkHtmlRenderer(output_dir=tmp_path, image_width=900)

    renderer.render(
        r"""# 视频标题

## 硅碳电池
- 比容量为 \(372\ \mathrm{mAh/g}\)，能量为 $E=mc^2$。

\[
\frac{3579\ \mathrm{mAh}}{g}
\]
""",
        base_filename="math-summary",
        enable_split=False,
    )

    html = str(captured["html"])
    assert html.count('class="math-inline"') == 2
    assert 'class="math-block"' in html
    assert 'class="math-display"' in html
    assert html.count("data:image/png;base64,") == 3
    assert "<script" not in html
    assert "disable-javascript" in captured["options"]


def test_wkhtml_math_parser_ignores_code() -> None:
    html = _markdown_to_html(
        r"""`$inline_code$`

```text
\[
block_code
\]
```

\(x^2\)
""",
        max_math_width=780,
    )

    assert html.count('class="math-inline"') == 1
    assert "<code>$inline_code$</code>" in html
    assert "block_code" in html
    assert 'class="math-block"' not in html


def test_wkhtml_invalid_math_falls_back_to_visible_source() -> None:
    html = _markdown_to_html(r"\(\unknowncommand{x}\)", max_math_width=780)

    assert 'class="math-source"' in html
    assert r"\(\unknowncommand{x}\)" in html
