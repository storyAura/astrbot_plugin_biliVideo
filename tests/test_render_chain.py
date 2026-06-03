"""RenderChain fallback behavior tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from bilivideo.core.exceptions import PartialRenderError, RenderError
from bilivideo.render.chain import RenderChain


def test_chain_falls_through_failing_backend(tmp_path) -> None:
    chain = RenderChain(output_dir=str(tmp_path), image_width=800)

    class _Failing:
        def render(self, *args, **kwargs):
            raise RenderError("nope")

    class _Working:
        def __init__(self) -> None:
            self.calls = 0

        def render(self, *args, **kwargs):
            self.calls += 1
            (Path(tmp_path) / f"{kwargs['base_filename']}.png").write_bytes(b"fake")
            return [Path(tmp_path) / f"{kwargs['base_filename']}.png"]

    working = _Working()
    chain._backends = [("first", _Failing()), ("second", working)]
    out = chain.render(
        "# test\n\n## 章节\n内容",
        base_filename="t",
        max_cards_per_image=6,
        enable_split=False,
    )
    assert len(out) == 1
    assert working.calls == 1


def test_chain_raises_when_all_fail(tmp_path) -> None:
    chain = RenderChain(output_dir=str(tmp_path))

    class _Failing:
        def render(self, *args, **kwargs):
            raise RenderError("dead")

    chain._backends = [("a", _Failing()), ("b", _Failing())]
    try:
        chain.render(
            "# t\n\nbody",
            base_filename="x",
            max_cards_per_image=6,
            enable_split=False,
        )
    except RenderError as exc:
        assert "all image backends failed" in str(exc)
    else:
        raise AssertionError("expected RenderError")


def test_chain_tries_next_backend_after_partial_render(tmp_path) -> None:
    chain = RenderChain(output_dir=str(tmp_path), image_width=800)
    partial_path = Path(tmp_path) / "partial_p2.png"
    partial_path.write_bytes(b"fake")

    class _Partial:
        def render(self, *args, **kwargs):
            raise PartialRenderError(
                "page 1 failed",
                generated_paths=[partial_path],
                failed_pages=[1],
            )

    class _Working:
        def render(self, *args, **kwargs):
            out = Path(tmp_path) / f"{kwargs['base_filename']}.png"
            out.write_bytes(b"ok")
            return [out]

    chain._backends = [("first", _Partial()), ("second", _Working())]
    out = chain.render(
        "# test\n\n## 章节\n内容",
        base_filename="t",
        max_cards_per_image=6,
        enable_split=True,
    )

    assert out == [Path(tmp_path) / "t.png"]


def test_chain_keeps_partial_paths_when_no_complete_backend(tmp_path) -> None:
    chain = RenderChain(output_dir=str(tmp_path), image_width=800)
    partial_path = Path(tmp_path) / "partial_p2.png"
    partial_path.write_bytes(b"fake")

    class _Partial:
        def render(self, *args, **kwargs):
            raise PartialRenderError(
                "page 1 failed",
                generated_paths=[partial_path],
                failed_pages=[1],
            )

    class _Failing:
        def render(self, *args, **kwargs):
            raise RenderError("dead")

    chain._backends = [("first", _Partial()), ("second", _Failing())]

    try:
        chain.render(
            "# test\n\n## 章节\n内容",
            base_filename="t",
            max_cards_per_image=6,
            enable_split=True,
        )
    except PartialRenderError as exc:
        assert exc.generated_paths == [partial_path]
        assert exc.failed_pages == [1]
    else:
        raise AssertionError("expected PartialRenderError")


def test_chain_keeps_best_partial_when_multiple_backends_partial(tmp_path) -> None:
    chain = RenderChain(output_dir=str(tmp_path), image_width=800)
    path_a = Path(tmp_path) / "a_p2.png"
    path_b = Path(tmp_path) / "a_p3.png"
    path_c = Path(tmp_path) / "b_p2.png"
    for path in (path_a, path_b, path_c):
        path.write_bytes(b"fake")

    class _BetterPartial:
        def render(self, *args, **kwargs):
            raise PartialRenderError(
                "one page failed",
                generated_paths=[path_a, path_b],
                failed_pages=[1],
            )

    class _WorsePartial:
        def render(self, *args, **kwargs):
            raise PartialRenderError(
                "two pages failed",
                generated_paths=[path_c],
                failed_pages=[1, 3],
            )

    chain._backends = [("better", _BetterPartial()), ("worse", _WorsePartial())]

    try:
        chain.render(
            "# test\n\n## 章节\n内容",
            base_filename="t",
            max_cards_per_image=6,
            enable_split=True,
        )
    except PartialRenderError as exc:
        assert exc.generated_paths == [path_a, path_b]
        assert exc.failed_pages == [1]
    else:
        raise AssertionError("expected PartialRenderError")


def test_chain_skips_unavailable_backends(tmp_path) -> None:
    """Unavailable renderers are reported but not listed as ready."""

    with (
        patch("bilivideo.render.chain._wkhtmltoimage_path", return_value=None),
        patch("bilivideo.render.chain.check_pillow_ready", return_value=(False, "no CJK font")),
    ):
        chain = RenderChain(output_dir=str(tmp_path))
    assert chain.available_backends == []
    assert chain.backend_diagnostics["wkhtmltopdf"] == "missing wkhtmltoimage on PATH"
    assert chain.backend_diagnostics["pillow"] == "unavailable: no CJK font"


def test_chain_reports_pillow_ready(tmp_path) -> None:
    with (
        patch("bilivideo.render.chain._wkhtmltoimage_path", return_value=None),
        patch("bilivideo.render.chain.check_pillow_ready", return_value=(True, "font=/tmp/font.ttc")),
    ):
        chain = RenderChain(output_dir=str(tmp_path))
    assert chain.available_backends == ["pillow"]
    assert chain.backend_diagnostics["pillow"] == "ready font=/tmp/font.ttc"
