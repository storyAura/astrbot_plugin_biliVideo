"""End-to-end orchestrator test using stub HTTP / pipeline / LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from bilivideo.core.config import PluginConfig
from bilivideo.core.exceptions import LLMError
from bilivideo.core.types import (
    AudioDownloadResult,
    TranscriptResult,
    TranscriptSegment,
    VideoInfo,
)
from bilivideo.llm.structured_summary import StructuredSummaryAttempt
from bilivideo.summarize.orchestrator import SummaryOrchestrator
from bilivideo.transcription.pipeline import PipelineOutput

# ──────────────────────── stubs ────────────────────────


class _StubLLM:
    def __init__(self, response: str = "# 视频标题 - UP\n\n## 章节A\n要点 *Content-[02:30]*\n") -> None:
        self.response = response
        self.calls: list[str] = []

    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
        self.calls.append(prompt)
        return self.response


class _ErrorLLM:
    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
        raise LLMError("boom")


class _StructuredStubLLM:
    def __init__(self, attempt: StructuredSummaryAttempt, fallback: str = "") -> None:
        self.attempt = attempt
        self.fallback = fallback
        self.structured_calls: list[str] = []
        self.structured_styles: list[str] = []
        self.plain_calls: list[str] = []

    async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
        self.plain_calls.append(prompt)
        return self.fallback

    async def chat_structured_summary(
        self,
        prompt: str,
        *,
        include_ai_summary: bool,
        style: str,
        session_id: str | None = None,
    ) -> StructuredSummaryAttempt:
        self.structured_calls.append(prompt)
        self.structured_styles.append(style)
        return self.attempt


class _StubPipeline:
    def __init__(self, output: PipelineOutput, *, raise_exc: Exception | None = None) -> None:
        self.output = output
        self.raise_exc = raise_exc
        self.cleanup_calls: list[Any] = []

    async def fetch(self, video_url: str, **kwargs: Any) -> PipelineOutput:
        if self.raise_exc:
            raise self.raise_exc
        return self.output

    def cleanup_audio(self, audio: Any) -> None:
        self.cleanup_calls.append(audio)


@dataclass
class _StubHTTP:
    """No-op HTTP client stub. The orchestrator only calls `get_video_info`
    on it via the api.endpoints helper, which we monkeypatch separately.
    """

    cookies: dict[str, str] = None  # type: ignore[assignment]


# ──────────────────────── fixtures ────────────────────────


def _make_pipeline_output(*, with_audio: bool = False) -> PipelineOutput:
    transcript = TranscriptResult(
        language="zh",
        full_text="hello world",
        segments=(
            TranscriptSegment(start=0, end=5, text="hello"),
            TranscriptSegment(start=5, end=10, text="world"),
        ),
    )
    audio = (
        AudioDownloadResult(
            file_path="/tmp/x.mp3",
            title="测试视频",
            duration=30.0,
            cover_url=None,
            platform="bilibili",
            video_id="BV1xx411c7mD",
            raw_info={"tags": ["python", "教程"]},
        )
        if with_audio
        else None
    )
    return PipelineOutput(transcript=transcript, audio=audio)


def _patch_get_video_info(monkeypatch, info: VideoInfo | None) -> None:
    async def _stub(http, bvid):
        if info is None:
            from bilivideo.core.exceptions import BiliVideoError

            raise BiliVideoError("not found")
        return info

    monkeypatch.setattr(
        "bilivideo.summarize.orchestrator.get_video_info", _stub
    )


# ──────────────────────── tests ────────────────────────


@pytest.mark.asyncio
async def test_happy_path_with_subtitle(monkeypatch) -> None:
    config = PluginConfig.from_mapping({"enable_link": True, "max_note_length": 3000})
    info = VideoInfo(bvid="BV1xx411c7mD", title="测试视频", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)

    pipeline = _StubPipeline(_make_pipeline_output(with_audio=False))
    llm = _StubLLM()

    orch = SummaryOrchestrator(config=config, llm=llm, pipeline=pipeline, http_client=_StubHTTP())  # type: ignore[arg-type]
    result = await orch.generate("https://www.bilibili.com/video/BV1xx411c7mD")

    assert result.video_info is info
    assert result.used_subtitle is True
    assert "[02:30]" in result.markdown  # timestamp marker replaced without unsupported glyphs
    assert pipeline.cleanup_calls == [None]  # no audio to clean
    assert len(llm.calls) == 1
    assert "BV1xx411c7mD" not in llm.calls[0]  # we don't leak BVID into prompt directly
    assert "submit_video_summary" not in llm.calls[0]  # custom/plain providers stay legacy-only


@pytest.mark.asyncio
async def test_astrbot_structured_summary_produces_stable_timestamps(monkeypatch) -> None:
    config = PluginConfig.from_mapping(
        {"enable_link": True, "enable_summary": True, "note_style": "concise"}
    )
    info = VideoInfo(bvid="BV1structured", title="测试视频", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)
    payload = {
        "title": "测试视频 - UP",
        "chapters": [
            {
                "title": "开场",
                "timestamp_seconds": 0,
                "body_markdown": r"- 公式 $\frac{1}{2}$\n- 换行后的结论",
            },
            {"title": "结尾", "timestamp_seconds": 5, "body_markdown": "结论"},
        ],
        "ai_summary": "整体总结",
    }
    llm = _StructuredStubLLM(StructuredSummaryAttempt(arguments=payload))
    pipeline = _StubPipeline(_make_pipeline_output())
    orch = SummaryOrchestrator(
        config=config, llm=llm, pipeline=pipeline, http_client=_StubHTTP()  # type: ignore[arg-type]
    )

    result = await orch.generate("https://www.bilibili.com/video/BV1structured")

    assert "## 开场 [00:00]" in result.markdown
    assert "## 结尾 [00:05]" in result.markdown
    assert "$\\frac{1}{2}$" in result.markdown
    assert "- 公式 $\\frac{1}{2}$\n- 换行后的结论" in result.markdown
    assert r"\n- 换行后的结论" not in result.markdown
    assert "⏱" not in result.markdown
    assert len(llm.structured_calls) == 1
    assert llm.structured_styles == ["concise"]
    assert llm.plain_calls == []
    assert "00:05 | 5s - world" in llm.structured_calls[0]


@pytest.mark.asyncio
async def test_invalid_structured_summary_falls_back_to_legacy_prompt(monkeypatch) -> None:
    config = PluginConfig.from_mapping({"enable_link": True})
    info = VideoInfo(bvid="BV1fallback", title="测试视频", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)
    invalid_payload = {
        "title": "测试视频 - UP",
        "chapters": [
            {"title": "越界", "timestamp_seconds": 999, "body_markdown": "内容"}
        ],
        "ai_summary": "总结",
    }
    llm = _StructuredStubLLM(
        StructuredSummaryAttempt(arguments=invalid_payload),
        fallback="# 测试视频 - UP\n\n## 章节 *Content-[00:05]*\n内容",
    )
    pipeline = _StubPipeline(_make_pipeline_output())
    orch = SummaryOrchestrator(
        config=config, llm=llm, pipeline=pipeline, http_client=_StubHTTP()  # type: ignore[arg-type]
    )

    result = await orch.generate("https://www.bilibili.com/video/BV1fallback")

    assert "## 章节 [00:05]" in result.markdown
    assert len(llm.structured_calls) == 1
    assert len(llm.plain_calls) == 1
    assert "Content-[mm:ss]" in llm.plain_calls[0]


@pytest.mark.asyncio
async def test_detailed_summary_over_twenty_chapters_does_not_fall_back(monkeypatch) -> None:
    config = PluginConfig.from_mapping({"enable_link": True, "note_style": "detailed"})
    info = VideoInfo(bvid="BV1many", title="测试视频", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)
    payload = {
        "title": "测试视频 - UP",
        "chapters": [
            {"title": f"章节 {index}", "timestamp_seconds": 0, "body_markdown": "- 内容"}
            for index in range(21)
        ],
        "ai_summary": "总结",
    }
    llm = _StructuredStubLLM(
        StructuredSummaryAttempt(arguments=payload),
        fallback="# 不应进入 Markdown 回退",
    )
    pipeline = _StubPipeline(_make_pipeline_output())
    orch = SummaryOrchestrator(
        config=config, llm=llm, pipeline=pipeline, http_client=_StubHTTP()  # type: ignore[arg-type]
    )

    result = await orch.generate("https://www.bilibili.com/video/BV1many")

    assert "## 章节 20 [00:00]" in result.markdown
    assert len(llm.structured_calls) == 1
    assert llm.plain_calls == []


@pytest.mark.asyncio
async def test_structured_and_fallback_requests_have_independent_timeouts(monkeypatch) -> None:
    from bilivideo.summarize import orchestrator as orch_mod

    timeouts: list[float] = []

    async def _record_wait_for(awaitable, *, timeout):
        timeouts.append(timeout)
        return await awaitable

    monkeypatch.setattr(orch_mod.asyncio, "wait_for", _record_wait_for)
    invalid_payload = {
        "title": "标题",
        "chapters": [
            {"title": "越界", "timestamp_seconds": 999, "body_markdown": "内容"}
        ],
        "ai_summary": "总结",
    }
    llm = _StructuredStubLLM(
        StructuredSummaryAttempt(arguments=invalid_payload),
        fallback="# Markdown 回退成功",
    )
    orch = SummaryOrchestrator(
        config=PluginConfig.from_mapping({"enable_link": True}),
        llm=llm,
        pipeline=_StubPipeline(_make_pipeline_output()),
        http_client=_StubHTTP(),  # type: ignore[arg-type]
    )

    markdown = await orch._request_markdown(
        legacy_prompt="legacy",
        structured_prompt="structured",
        max_timestamp_seconds=10,
    )

    assert markdown == "# Markdown 回退成功"
    assert timeouts == [
        orch_mod.LLM_CHAT_TIMEOUT_SECONDS,
        orch_mod.LLM_CHAT_TIMEOUT_SECONDS,
    ]


@pytest.mark.asyncio
async def test_timestamp_disabled_never_requests_structured_output(monkeypatch) -> None:
    config = PluginConfig.from_mapping({"enable_link": False})
    info = VideoInfo(bvid="BV1plain", title="测试视频", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)
    llm = _StructuredStubLLM(
        StructuredSummaryAttempt(arguments={}), fallback="# 测试视频\n\n普通总结"
    )
    pipeline = _StubPipeline(_make_pipeline_output())
    orch = SummaryOrchestrator(
        config=config, llm=llm, pipeline=pipeline, http_client=_StubHTTP()  # type: ignore[arg-type]
    )

    result = await orch.generate("https://www.bilibili.com/video/BV1plain")

    assert result.markdown.startswith("# 测试视频")
    assert llm.structured_calls == []
    assert len(llm.plain_calls) == 1


@pytest.mark.asyncio
async def test_happy_path_with_audio(monkeypatch) -> None:
    config = PluginConfig.from_mapping({})
    info = VideoInfo(bvid="BV1abc", title="t", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)

    output = _make_pipeline_output(with_audio=True)
    pipeline = _StubPipeline(output)
    llm = _StubLLM()
    orch = SummaryOrchestrator(config=config, llm=llm, pipeline=pipeline, http_client=_StubHTTP())  # type: ignore[arg-type]
    result = await orch.generate("https://www.bilibili.com/video/BV1abc")

    assert result.used_subtitle is False
    assert pipeline.cleanup_calls == [output.audio]


@pytest.mark.asyncio
async def test_llm_failure_propagates(monkeypatch) -> None:
    config = PluginConfig.from_mapping({})
    _patch_get_video_info(monkeypatch, None)

    pipeline = _StubPipeline(_make_pipeline_output())
    orch = SummaryOrchestrator(
        config=config, llm=_ErrorLLM(), pipeline=pipeline, http_client=_StubHTTP()  # type: ignore[arg-type]
    )
    with pytest.raises(LLMError):
        await orch.generate("https://www.bilibili.com/video/BV1abc")
    # cleanup must still happen
    assert pipeline.cleanup_calls == [None]


@pytest.mark.asyncio
async def test_truncation_when_oversized(monkeypatch) -> None:
    # max_note_length below 500 is clamped up to 500 by PluginConfig
    config = PluginConfig.from_mapping({"max_note_length": 500, "enable_link": False})
    info = VideoInfo(bvid="BV1abc", title="t", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)

    long_md = "# t\n\n" + "## 章节\n" + ("内容 " * 400)  # ~1200 chars
    pipeline = _StubPipeline(_make_pipeline_output())
    orch = SummaryOrchestrator(
        config=config, llm=_StubLLM(long_md), pipeline=pipeline, http_client=_StubHTTP()  # type: ignore[arg-type]
    )
    result = await orch.generate("https://www.bilibili.com/video/BV1abc")
    assert "内容过长提示" in result.markdown
    # original length was ~1200; truncated to ~500 + tail message (~150)
    assert len(result.markdown) < 1100


@pytest.mark.asyncio
async def test_summary_is_cached_per_bvid(monkeypatch) -> None:
    config = PluginConfig.from_mapping({})
    info = VideoInfo(bvid="BV1xx411c7mD", title="t", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)

    pipeline = _StubPipeline(_make_pipeline_output())
    llm = _StubLLM()
    orch = SummaryOrchestrator(config=config, llm=llm, pipeline=pipeline, http_client=_StubHTTP())  # type: ignore[arg-type]

    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    first = await orch.generate(url)
    second = await orch.generate(url)

    assert second is first  # second request served straight from cache
    assert len(llm.calls) == 1  # LLM invoked only once
    assert len(pipeline.cleanup_calls) == 1  # pipeline ran only once

    await orch.clear_cache()
    await orch.generate(url)
    assert len(llm.calls) == 2  # regenerated after the cache was cleared


@pytest.mark.asyncio
async def test_llm_timeout_surfaces_specific_error(monkeypatch) -> None:
    import asyncio as _asyncio

    from bilivideo.core.exceptions import BiliVideoError
    from bilivideo.summarize import orchestrator as orch_mod

    config = PluginConfig.from_mapping({})
    info = VideoInfo(bvid="BV1abc", title="t", owner_name="UP")
    _patch_get_video_info(monkeypatch, info)
    monkeypatch.setattr(orch_mod, "LLM_CHAT_TIMEOUT_SECONDS", 0.05)

    class _SlowLLM:
        async def chat(self, prompt: str, *, session_id: str | None = None) -> str:
            await _asyncio.sleep(1)
            return "too late"

    output = _make_pipeline_output(with_audio=True)
    pipeline = _StubPipeline(output)
    orch = SummaryOrchestrator(
        config=config, llm=_SlowLLM(), pipeline=pipeline, http_client=_StubHTTP()  # type: ignore[arg-type]
    )
    with pytest.raises(BiliVideoError) as excinfo:
        await orch.generate("https://www.bilibili.com/video/BV1abc")

    assert "AI 总结超时" in excinfo.value.user_message
    assert pipeline.cleanup_calls == [output.audio]  # cleanup still runs in finally
