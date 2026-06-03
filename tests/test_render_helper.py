"""Render helper fallback tests."""

from __future__ import annotations

from bilivideo.core.config import PluginConfig
from bilivideo.core.exceptions import PartialRenderError, RenderError
from bilivideo.handlers import _render_helper


class _ImageMeta(type):
    def __getattr__(cls, name: str):
        if name == "fromFileSystem":
            return cls.from_file_system
        raise AttributeError(name)


class _Image(metaclass=_ImageMeta):
    def __init__(self, path: str) -> None:
        self.path = path

    @classmethod
    def from_file_system(cls, path: str):
        return cls(path)


class _Plain:
    def __init__(self, text: str) -> None:
        self.text = text


class _Renderer:
    def __init__(self, paths=None, failed_pages=None, error: Exception | None = None) -> None:
        self.error = error
        self.paths = paths
        self.failed_pages = failed_pages

    def render(self, *args, **kwargs):
        if self.error is not None:
            raise self.error
        raise PartialRenderError(
            "partial",
            generated_paths=list(self.paths),
            failed_pages=list(self.failed_pages),
            page_errors={page: f"page {page} exploded" for page in self.failed_pages},
        )


class _Services:
    def __init__(self, renderer) -> None:
        self.config = PluginConfig(output_image=True)
        self.renderer = renderer


def test_partial_render_returns_components_without_raw_string(tmp_path, monkeypatch) -> None:
    image = tmp_path / "note_p2.png"
    image.write_bytes(b"fake")
    monkeypatch.setattr(_render_helper, "Image", _Image)
    monkeypatch.setattr(_render_helper, "Plain", _Plain)

    rendered = _render_helper.render_note_components(
        _Services(_Renderer([image], [1])),
        "# 标题\n\n## 一\n内容",
    )

    assert isinstance(rendered, list)
    assert isinstance(rendered[0], _Image)
    assert isinstance(rendered[1], _Plain)
    assert "第 1 页图片生成失败" in rendered[1].text
    assert "page 1 exploded" in rendered[1].text
    assert not any(isinstance(item, str) for item in rendered)


def test_render_error_returns_visible_fallback_text(monkeypatch) -> None:
    monkeypatch.setattr(_render_helper, "Image", _Image)
    rendered = _render_helper.render_note_components(
        _Services(_Renderer(error=RenderError("no CJK font"))),
        "# 标题",
    )

    assert isinstance(rendered, str)
    assert "图片渲染失败" in rendered
    assert "no CJK font" in rendered


def test_invalid_paths_return_visible_fallback_text(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "missing.png"
    monkeypatch.setattr(_render_helper, "Image", _Image)

    class _InvalidPathRenderer:
        def render(self, *args, **kwargs):
            return [missing]

    rendered = _render_helper.render_note_components(
        _Services(_InvalidPathRenderer()),
        "# 标题",
    )

    assert isinstance(rendered, str)
    assert "图片渲染失败" in rendered
    assert str(missing) in rendered


def test_unexpected_exception_returns_fallback_text(monkeypatch) -> None:
    """A non-RenderError surprise must still degrade to visible text."""

    monkeypatch.setattr(_render_helper, "Image", _Image)

    class _BoomRenderer:
        def render(self, *args, **kwargs):
            raise ValueError("totally unexpected")

    rendered = _render_helper.render_note_components(
        _Services(_BoomRenderer()), "# 标题\n\n内容"
    )

    assert isinstance(rendered, str)
    assert "图片渲染失败" in rendered
    assert "totally unexpected" in rendered
