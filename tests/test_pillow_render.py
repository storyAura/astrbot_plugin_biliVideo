"""End-to-end Pillow render + helper unit tests.

These exercise the real paint path (the bundled CJK font guarantees a usable
font is always present) so geometry/wrapping regressions that would clip text
or crash rendering are caught.
"""

from __future__ import annotations

from PIL import Image

from bilivideo.render import pillow_renderer as pr
from bilivideo.render.pillow_renderer import PillowRenderer


def _render(tmp_path, markdown: str, *, name: str = "note", width: int = 1400):
    renderer = PillowRenderer(output_dir=tmp_path, image_width=width)
    return renderer._render_one(markdown, name, page_label=None, total=1)


def test_renders_valid_png_within_width(tmp_path) -> None:
    md = "# 测试标题\n\n## 章节一\n这是正文内容。\n\n### 小标题\n- 列表项一\n- 列表项二"
    out = _render(tmp_path, md)
    assert len(out) == 1
    with Image.open(out[0]) as img:
        img.verify()  # not a truncated/corrupt PNG
    with Image.open(out[0]) as img:
        assert img.width == 1400
        assert img.height > 200


def test_long_title_heading_h3_do_not_crash(tmp_path) -> None:
    # Each of these would clip off the right edge if drawn on a single line.
    md = (
        f"# {'超长视频标题' * 20}\n\n"
        f"## {'很长的章节标题' * 18}\n\n"
        f"### {'很长的小节标题' * 18}\n"
        "正文内容。"
    )
    out = _render(tmp_path, md)
    with Image.open(out[0]) as img:
        assert img.width == 1400
        assert img.height > 200


def test_wrap_splits_long_text_without_dropping_content(tmp_path) -> None:
    renderer = PillowRenderer(output_dir=tmp_path)
    font, _ = pr._load_font(28)
    lines = renderer._wrap("文" * 200, font=font, max_width=600)
    assert len(lines) > 1  # actually wrapped
    assert "".join(lines) == "文" * 200  # no characters lost


def test_taller_content_yields_taller_image(tmp_path) -> None:
    short = _render(tmp_path, "# 标题\n\n## 章节\n内容", name="short")
    big_md = "# 标题\n" + "".join(
        f"\n## 章节{i}\n" + "正文内容。\n" * 6 for i in range(5)
    )
    big = _render(tmp_path, big_md, name="big")
    with Image.open(short[0]) as a, Image.open(big[0]) as b:
        assert b.height > a.height


def test_emoji_title_is_rendered_without_crash(tmp_path) -> None:
    out = _render(tmp_path, "# 📺 教程🔥合集\n\n## 章节\n✅ 完成 内容")
    with Image.open(out[0]) as img:
        assert img.width == 1400


def test_leading_timestamp_line_renders(tmp_path) -> None:
    # Exercises the accent-colored timestamp split in _draw_line.
    md = "# 标题\n\n## 章节\n- 12:34 关键时刻说明\n- 普通要点"
    out = _render(tmp_path, md)
    with Image.open(out[0]) as img:
        assert img.width == 1400


def test_empty_markdown_renders_placeholder(tmp_path) -> None:
    out = _render(tmp_path, "")
    with Image.open(out[0]) as img:
        assert img.width == 1400
        assert img.height > 0


class TestStripUnsupportedGlyphs:
    def test_removes_emoji_keeps_cjk(self) -> None:
        assert pr._strip_unsupported_glyphs("📺 视频总结 🔥") == "视频总结"

    def test_keeps_bullets_arrows_quotes_dashes(self) -> None:
        text = "• 要点 → 结果 “引用” —— 破折号"
        assert pr._strip_unsupported_glyphs(text) == text

    def test_removes_clock_symbol(self) -> None:
        # ⏱ (U+23F1) is outside the bundled GB2312 subset → would be tofu.
        assert "⏱" not in pr._strip_unsupported_glyphs("⏱ 12:34 内容")

    def test_empty_is_safe(self) -> None:
        assert pr._strip_unsupported_glyphs("") == ""


class TestTimestampRegex:
    def test_matches_plain(self) -> None:
        assert pr._TS_RE.match("12:34 内容")

    def test_matches_bracketed(self) -> None:
        assert pr._TS_RE.match("[01:02] 内容")

    def test_matches_hms(self) -> None:
        assert pr._TS_RE.match("1:02:03 内容")

    def test_does_not_match_prose(self) -> None:
        assert pr._TS_RE.match("这是正文内容") is None


class TestHexToRgb:
    def test_valid_six_digit(self) -> None:
        assert PillowRenderer._hex_to_rgb("#60a5fa") == (96, 165, 250)

    def test_three_digit_expands(self) -> None:
        assert PillowRenderer._hex_to_rgb("#abc") == (170, 187, 204)

    def test_rgba_string_falls_back_to_accent(self) -> None:
        # The theme pairs each border with an rgba() string; feeding one must
        # not raise — it returns the safe accent color instead.
        assert PillowRenderer._hex_to_rgb("rgba(96,165,250,.10)") == PillowRenderer.ACCENT_FG

    def test_garbage_falls_back(self) -> None:
        assert PillowRenderer._hex_to_rgb("not-a-color") == PillowRenderer.ACCENT_FG
