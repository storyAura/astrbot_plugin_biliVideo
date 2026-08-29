"""Semantic coverage for the CommonMark AST adapter."""

from __future__ import annotations

from bilivideo.render.pillow_renderer import _parse_markdown_blocks


def test_parses_inline_styles_and_both_math_delimiters() -> None:
    blocks = _parse_markdown_blocks(
        r"""# 标题

## 章节
正文 **粗体**、*斜体*、`代码`、$E=mc^2$ 和 \(x^2\)。

\[
372\ \text{mAh/g}
\]
"""
    )

    paragraph = next(block for block in blocks if block.kind == "p")
    assert any(span.bold and span.text == "粗体" for span in paragraph.spans)
    assert any(span.italic and span.text == "斜体" for span in paragraph.spans)
    assert any(span.kind == "code" and span.text == "代码" for span in paragraph.spans)
    assert [span.text for span in paragraph.spans if span.kind == "math"] == ["E=mc^2", "x^2"]

    display_math = next(block for block in blocks if block.kind == "math")
    assert display_math.text == r"372\ \text{mAh/g}"


def test_parses_nested_lists_quotes_code_and_tables() -> None:
    blocks = _parse_markdown_blocks(
        """1. 第一项
   - 嵌套项

> 引用

```python
print(1)
```

| 名称 | 数值 |
|---|---:|
| 电池 | 8000 |
"""
    )

    list_items = [block for block in blocks if block.kind == "li"]
    assert [(block.marker, block.indent, block.text) for block in list_items] == [
        ("1.", 0, "第一项"),
        ("•", 1, "嵌套项"),
    ]
    assert next(block for block in blocks if block.kind == "quote").text == "引用"
    assert next(block for block in blocks if block.kind == "code").text == "print(1)"

    table = next(block for block in blocks if block.kind == "table")
    assert len(table.rows) == 2
    assert table.rows[0].header is True
    assert table.rows[1].cells[1].align == "right"


def test_raw_html_is_plain_text_and_cannot_load_resources() -> None:
    blocks = _parse_markdown_blocks('<img src="file:///etc/passwd" onerror="run()">')
    assert len(blocks) == 1
    assert blocks[0].kind == "p"
    assert "file:///etc/passwd" in blocks[0].text


def test_block_math_after_list_does_not_require_blank_lines() -> None:
    blocks = _parse_markdown_blocks(
        r"""- 理论比容量：
\[
372\ \mathrm{mAh/g}
\]
- 下一项
"""
    )

    assert [block.kind for block in blocks] == ["li", "math", "li"]
    assert blocks[1].text == r"372\ \mathrm{mAh/g}"


def test_dollar_math_boundaries_are_not_changed_inside_code_fences() -> None:
    blocks = _parse_markdown_blocks(
        r"""- 公式：
$$
x^2
$$

```text
\[
not math
\]
```
"""
    )

    assert next(block for block in blocks if block.kind == "math").text == "x^2"
    code = next(block for block in blocks if block.kind == "code")
    assert code.text == "\\[\nnot math\n\\]"
