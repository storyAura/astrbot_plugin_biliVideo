"""Pillow renderer font fallback tests."""

from __future__ import annotations

from bilivideo.render import pillow_renderer


def test_pillow_ready_without_cjk_font_uses_fallback_font(monkeypatch, tmp_path) -> None:
    fallback = tmp_path / "Fallback.ttf"
    fallback.write_bytes(b"fake")

    import PIL.ImageFont

    def _fake_truetype(path, _size):
        assert path == str(fallback)
        return object()

    monkeypatch.setattr(pillow_renderer, "_find_cjk_font", lambda: None)
    monkeypatch.setattr(pillow_renderer, "_find_fallback_font", lambda: str(fallback))
    monkeypatch.setattr(PIL.ImageFont, "truetype", _fake_truetype)

    ready, reason = pillow_renderer.check_pillow_ready()

    assert ready
    assert "fallback_font" in reason
    assert "no CJK font discovered" in reason


def test_pillow_ready_never_blocks_without_any_font(monkeypatch) -> None:
    # No CJK font and no fallback font -> still ready via Pillow's built-in
    # default, so image rendering never degrades to plain text on that account.
    monkeypatch.setattr(pillow_renderer, "_find_cjk_font", lambda: None)
    monkeypatch.setattr(pillow_renderer, "_find_fallback_font", lambda: None)

    ready, reason = pillow_renderer.check_pillow_ready()

    assert ready
    assert "Pillow default font" in reason
