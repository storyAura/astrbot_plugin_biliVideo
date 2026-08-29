"""Prompt templates for note generation.

Centralizing the prompt makes it trivial to A/B different copy and to share
the core requirements between the three styles. The original prompt's
intent is preserved verbatim where it mattered.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.types import TranscriptSegment

MARKDOWN_OUTPUT_INSTRUCTIONS = """\
输出说明:
- 仅返回最终的 **Markdown 内容**。
- **不要**将输出包裹在代码块中(例如:```` ```markdown ````,```` ``` ````)。
- 在生成 Markdown 时,避免将编号标题写成有序列表的格式,以免解析错误。"""

STRUCTURED_OUTPUT_INSTRUCTIONS = """\
输出说明:
- 当 `submit_video_summary` 工具可用时,必须调用该工具,不要输出普通正文。
- `timestamp_seconds` 必须复制对应转录片段的整数秒,章节必须按时间递增。
- `body_markdown` 中必须使用真实换行,不要输出字面量 `\\n` 或 `\\r\\n`。
- 如果运行环境没有提供该工具,则回退为最终 Markdown 内容:第一行使用 h1,
  后续章节使用 h2,且不要包裹代码块。"""

MARKDOWN_FORMAT_INSTRUCTIONS = """\
格式要求(非常重要):
- **第一行必须是 h1 标题**,格式为 `# 视频标题 - 作者名`。
- 使用 `## 章节标题` 来分隔不同内容板块。
- 不要使用多个 h1 标题,整篇总结只能有第一行那一个 h1。
- 每个板块内可以使用列表、引用块(> 引用)、**加粗** 和 *斜体* 来组织信息。
- 合理分段,避免单个板块内容过长。"""

STRUCTURED_FORMAT_INSTRUCTIONS = """\
工具参数要求(非常重要):
- `title` 填写视频标题和作者名,不要添加 Markdown 标题符号。
- 每个主要内容板块对应 `chapters` 中的一项。
- `body_markdown` 可以使用列表、引用块、表格、加粗、斜体和 LaTeX,但不要包含 h1/h2。
- 合理分段,避免单个板块内容过长。"""


@dataclass(slots=True, frozen=True)
class SummaryStyleProfile:
    """One source of truth for prompt and tool-schema style constraints."""

    instruction: str
    max_chapters: int
    chapters_description: str
    body_description: str


SUMMARY_STYLE_PROFILES: dict[str, SummaryStyleProfile] = {
    "concise": SummaryStyleProfile(
        instruction="""\
**简洁模式(最高优先级)**:
- 全文只保留 5-8 个核心观点;内容确实不足时可以少于 5 个,不要为了凑数重复信息。
- 一个章节只表达一个核心观点,`body_markdown` 只写一个项目符号和一句完整的话。
- 省略背景铺垫、过程复述、次要例子和同义重复;数据只保留直接支撑结论的部分。
- 不得因通用的“完整性”要求扩写内容。""",
        max_chapters=8,
        chapters_description="最多 8 个核心观点；内容不足时可以更少，禁止凑数或重复。",
        body_description=(
            "只包含一个 Markdown 项目符号和一句简洁完整的话；"
            "不得展开背景、过程、次要例子或同义重复。"
        ),
    ),
    "detailed": SummaryStyleProfile(
        instruction="""\
**详细模式**:
- 按视频内容顺序完整覆盖主要主题,最多使用 20 个章节。
- 每章保留关键事实、必要例子、数据和论证过程,通常组织为 2-5 个项目符号。
- 删除广告、口头重复和无信息量的转场,不要逐句复述转录文本。""",
        max_chapters=20,
        chapters_description="按视频顺序完整覆盖主要主题，最多 20 个章节。",
        body_description=(
            "详细说明本章内容，通常使用 2-5 个项目符号；"
            "保留关键事实、必要例子、数据和论证过程，但不要逐句复述。"
        ),
    ),
    "professional": SummaryStyleProfile(
        instruction="""\
**专业模式**:
- 提炼背景、核心论点、关键数据和结论建议,最多使用 12 个章节。
- 每章使用 1-3 个项目符号,说明事实之间的关系和结论,避免堆积转录细节。
- 语言正式、逻辑清晰;只有影响结论的例子和数据才需要保留。""",
        max_chapters=12,
        chapters_description="围绕背景、核心论点、关键数据和结论组织，最多 12 个章节。",
        body_description=(
            "使用 1-3 个 Markdown 项目符号说明关键事实、关系和结论；"
            "避免堆积转录细节，只保留影响结论的例子和数据。"
        ),
    ),
}


def get_summary_style_profile(style: str | None) -> SummaryStyleProfile:
    """Return a validated style profile, defaulting to professional."""

    return SUMMARY_STYLE_PROFILES.get(style or "professional", SUMMARY_STYLE_PROFILES["professional"])

BASE_PROMPT = """\
你是一个专业的总结助手,擅长将视频转录内容整理成清晰、有条理且信息丰富的总结。

语言要求:
- 总结必须使用 **中文** 撰写。
- 专有名词、技术术语、品牌名称和人名应适当保留 **英文**。

视频标题:
{video_title}

视频标签:
{tags}

当前总结模式:
{style_instruction}

{output_instructions}

{format_instructions}

视频分段(格式:{segment_format}):

---
{segment_text}
---

你的任务:
根据上面的分段转录内容,生成结构化的总结,遵循以下原则:

1. **按模式取舍**:严格服从当前总结模式的信息密度和章节约束,不要擅自扩写。
2. **去除无关内容**:省略广告、填充词、问候语和不相关的言论。
3. **事实准确**:不得编造转录中不存在的数据、结论或因果关系。
4. **可读布局**:必要时使用项目符号,并保持段落简短。
5. 视频中提及的数学公式必须保留,并以 LaTeX 语法形式呈现。

额外重要的任务如下(每一个都必须严格完成):
"""

LINK_INSTRUCTION = "9. **原片跳转**: 为每个主要章节添加时间戳,使用格式 `*Content-[mm:ss]`。"

AI_SUMMARY_MARKDOWN_INSTRUCTION = (
    "🧠 在总结末尾添加 `## AI 总结`,用中文简短总结整个视频,不要重复章节内容。"
)
AI_SUMMARY_STRUCTURED_INSTRUCTION = (
    "🧠 在 `ai_summary` 字段中用中文简短总结整个视频,不要添加标题或重复章节内容。"
)


def format_time(seconds: float) -> str:
    """Format seconds as `mm:ss` or `h:mm:ss`."""

    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def render_segment_text(
    segments: tuple[TranscriptSegment, ...], *, include_seconds: bool = False
) -> str:
    if include_seconds:
        return "\n".join(
            f"{format_time(seg.start)} | {int(seg.start)}s - {seg.text.strip()}" for seg in segments
        )
    return "\n".join(f"{format_time(seg.start)} - {seg.text.strip()}" for seg in segments)


def build_prompt(
    *,
    title: str,
    segments: tuple[TranscriptSegment, ...],
    tags: str = "",
    style: str | None = None,
    enable_link: bool = False,
    enable_summary: bool = True,
    structured_output: bool = False,
) -> str:
    """Compose the final prompt sent to the LLM."""

    style_profile = get_summary_style_profile(style)
    body = BASE_PROMPT.format(
        video_title=title,
        segment_text=render_segment_text(segments, include_seconds=structured_output),
        tags=tags,
        output_instructions=(
            STRUCTURED_OUTPUT_INSTRUCTIONS if structured_output else MARKDOWN_OUTPUT_INSTRUCTIONS
        ),
        format_instructions=(
            STRUCTURED_FORMAT_INSTRUCTIONS
            if structured_output
            else MARKDOWN_FORMAT_INSTRUCTIONS
        ),
        segment_format=(
            "显示时间 | 整数秒s - 内容" if structured_output else "开始时间 - 内容"
        ),
        style_instruction=style_profile.instruction,
    )
    pieces = [body]
    if enable_link and not structured_output:
        pieces.append(LINK_INSTRUCTION)
    if enable_summary:
        pieces.append(
            AI_SUMMARY_STRUCTURED_INSTRUCTION
            if structured_output
            else AI_SUMMARY_MARKDOWN_INSTRUCTION
        )
    return "\n".join(pieces)
