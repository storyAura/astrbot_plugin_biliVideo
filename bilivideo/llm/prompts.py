"""Prompt templates for note generation.

Centralizing the prompt makes it trivial to A/B different copy and to share
the core requirements between the three styles. The original prompt's
intent is preserved verbatim where it mattered.
"""

from __future__ import annotations

from ..core.types import TranscriptSegment

BASE_PROMPT = """\
你是一个专业的总结助手,擅长将视频转录内容整理成清晰、有条理且信息丰富的总结。

语言要求:
- 总结必须使用 **中文** 撰写。
- 专有名词、技术术语、品牌名称和人名应适当保留 **英文**。

视频标题:
{video_title}

视频标签:
{tags}

输出说明:
- 仅返回最终的 **Markdown 内容**。
- **不要**将输出包裹在代码块中(例如:```` ```markdown ````,```` ``` ````)。
- 在生成 Markdown 时,避免将编号标题写成有序列表的格式,以免解析错误。

格式要求(非常重要):
- **第一行必须是 h1 标题**,格式为 `# 视频标题 - 作者名`。
- 使用 `## 章节标题` 来分隔不同内容板块。
- 不要使用多个 h1 标题,整篇总结只能有第一行那一个 h1。
- 每个板块内可以使用列表、引用块(> 引用)、**加粗** 和 *斜体* 来组织信息。
- 合理分段,避免单个板块内容过长。

视频分段(格式:开始时间 - 内容):

---
{segment_text}
---

你的任务:
根据上面的分段转录内容,生成结构化的总结,遵循以下原则:

1. **完整信息**:记录尽可能多的相关细节。
2. **去除无关内容**:省略广告、填充词、问候语和不相关的言论。
3. **保留关键细节**:保留重要事实、示例、结论和建议。
4. **可读布局**:必要时使用项目符号,并保持段落简短。
5. 视频中提及的数学公式必须保留,并以 LaTeX 语法形式呈现。

额外重要的任务如下(每一个都必须严格完成):
"""

LINK_INSTRUCTION = "9. **原片跳转**: 为每个主要章节添加时间戳,使用格式 `*Content-[mm:ss]`。"

AI_SUMMARY_INSTRUCTION = "🧠 在总结末尾,添加一个专业的 **AI 总结** — 用中文简短总结整个视频。"

NOTE_STYLES: dict[str, str] = {
    "concise": (
        "**简洁模式**: 仅提取核心观点和关键结论,每个章节用简短的要点概括。"
        "省略细节和举例,只保留最重要的信息。整体控制在 5-8 个要点以内。"
        "每个要点用一句话概括,使用 `## 章节标题` 来分隔不同板块。"
    ),
    "detailed": (
        "**详细模式**: 完整记录视频内容,每个部分都包含详细讨论。"
        "保留重要的例子、数据和论证过程。使用 `## 章节标题` 来分隔不同板块,"
        "每个板块内使用列表和引用块来组织信息。需要尽可能多的记录视频内容。"
    ),
    "professional": (
        "**专业模式**: 提供深度结构化分析,包含背景概述、核心论点、数据支撑和结论建议。"
        "使用 `## 章节标题` 来分隔不同板块(如:概述、核心内容、关键数据、总结与建议)。"
        "每个板块内使用列表、引用块和加粗来突出关键信息。语言正式、逻辑清晰。"
    ),
}


def format_time(seconds: float) -> str:
    """Format seconds as `mm:ss` or `h:mm:ss`."""

    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def render_segment_text(segments: tuple[TranscriptSegment, ...]) -> str:
    return "\n".join(f"{format_time(seg.start)} - {seg.text.strip()}" for seg in segments)


def build_prompt(
    *,
    title: str,
    segments: tuple[TranscriptSegment, ...],
    tags: str = "",
    style: str | None = None,
    enable_link: bool = False,
    enable_summary: bool = True,
) -> str:
    """Compose the final prompt sent to the LLM."""

    body = BASE_PROMPT.format(
        video_title=title,
        segment_text=render_segment_text(segments),
        tags=tags,
    )
    pieces = [body]
    if enable_link:
        pieces.append(LINK_INSTRUCTION)
    if enable_summary:
        pieces.append(AI_SUMMARY_INSTRUCTION)
    if style and style in NOTE_STYLES:
        pieces.append(NOTE_STYLES[style])
    return "\n".join(pieces)
