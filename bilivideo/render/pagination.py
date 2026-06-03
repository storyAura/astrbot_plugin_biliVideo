"""Split a long Markdown document into multiple renderable pages."""

from __future__ import annotations

DEFAULT_MAX_PAGE_CHARS = 12_000


def _chapter_cost(chapter: list[str]) -> int:
    text = "\n".join(chapter)
    return len(text) + max(1, len(chapter)) * 40


def _page_text(title: str, intro: str, chunks: list[str], *, continuation: bool) -> str:
    display_title = f"{title}(续)" if continuation else title
    prefix = f"# {display_title}\n\n"
    if intro and not continuation:
        prefix += f"{intro}\n\n"
    return (prefix + "\n\n".join(chunks)).rstrip()


def _split_oversize_chapter(chapter: list[str], max_page_chars: int) -> list[list[str]]:
    if _chapter_cost(chapter) <= max_page_chars:
        return [chapter]

    heading = chapter[0] if chapter and chapter[0].startswith("## ") else "## 章节"
    body_lines = chapter[1:] if chapter and chapter[0].startswith("## ") else chapter
    chunks: list[list[str]] = []
    current = [heading]
    current_cost = _chapter_cost(current)

    for block in _paragraph_blocks(body_lines):
        block_cost = _chapter_cost(block)
        if len(current) > 1 and current_cost + block_cost > max_page_chars:
            chunks.append(current)
            current = [f"{heading} (续)"]
            current_cost = _chapter_cost(current)
        if block_cost > max_page_chars:
            for piece in _hard_split_block(block, max_page_chars):
                if len(current) > 1 and current_cost + _chapter_cost(piece) > max_page_chars:
                    chunks.append(current)
                    current = [f"{heading} (续)"]
                    current_cost = _chapter_cost(current)
                current.extend(piece)
                current_cost += _chapter_cost(piece)
            continue
        current.extend(block)
        current_cost += block_cost

    if current:
        chunks.append(current)
    return chunks


def _paragraph_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks or [[]]


def _hard_split_block(lines: list[str], max_page_chars: int) -> list[list[str]]:
    text = "\n".join(lines)
    limit = max(500, max_page_chars - 400)
    return [[text[idx : idx + limit]] for idx in range(0, len(text), limit)]


def split_by_chapters(
    markdown_text: str,
    *,
    max_cards: int = 6,
    max_page_chars: int = DEFAULT_MAX_PAGE_CHARS,
) -> list[str]:
    """Split a Markdown document at `## ` boundaries into pages of up to
    `max_cards` chapters, preserving the document's `# h1` title across
    pages and an `（续）` suffix on continuations.

    `max_page_chars` keeps the first image from becoming much taller than
    later pages when early chapters contain most of the transcript detail.
    """

    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    title = "AI 视频总结"
    intro_lines: list[str] = []
    chapters: list[list[str]] = []
    current: list[str] = []

    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx < len(lines) and lines[idx].startswith("# "):
        title = lines[idx][2:].strip()
        idx += 1

    while idx < len(lines):
        line = lines[idx]
        if line.startswith("## "):
            break
        intro_lines.append(line)
        idx += 1

    intro = "\n".join(intro_lines).strip()

    while idx < len(lines):
        line = lines[idx]
        if line.startswith("## "):
            if current:
                chapters.append(current)
            current = [line]
        else:
            current.append(line)
        idx += 1
    if current:
        chapters.append(current)

    split_chapters: list[list[str]] = []
    for chapter in chapters:
        split_chapters.extend(_split_oversize_chapter(chapter, max_page_chars))
    chapters = split_chapters

    if not chapters:
        return [f"# {title}\n\n{intro}".rstrip()]

    pages: list[str] = []
    current: list[list[str]] = []
    current_cost = len(intro)
    continuation = False

    for chapter in chapters:
        chapter_cost = _chapter_cost(chapter)
        would_exceed_cards = len(current) >= max_cards
        would_exceed_chars = bool(current) and current_cost + chapter_cost > max_page_chars
        if would_exceed_cards or would_exceed_chars:
            pages.append(
                _page_text(
                    title,
                    intro,
                    ["\n".join(c) for c in current],
                    continuation=continuation,
                )
            )
            continuation = True
            current = []
            current_cost = 0
        current.append(chapter)
        current_cost += chapter_cost

    if current:
        pages.append(
            _page_text(
                title,
                intro,
                ["\n".join(c) for c in current],
                continuation=continuation,
            )
        )
    return pages
