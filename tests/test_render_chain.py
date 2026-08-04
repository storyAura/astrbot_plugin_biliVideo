"""Tests for renderer backend selection and delegation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bilivideo.core.exceptions import PartialRenderError, RenderError
from bilivideo.render.chain import RenderChain


def test_chain_prefers_wkhtml_and_does_not_initialize_python(tmp_path) -> None:
    with (
        patch("bilivideo.render.chain._wkhtmltoimage_path", return_value="/usr/bin/wkhtmltoimage"),
        patch("bilivideo.render.chain.check_pillow_ready") as check_python,
    ):
        chain = RenderChain(output_dir=str(tmp_path), image_width=800)

    check_python.assert_not_called()
    assert chain.available_backends == ["wkhtmltopdf"]
    assert chain.backend_diagnostics == {
        "wkhtmltopdf": "ready (/usr/bin/wkhtmltoimage)",
        "python": "standby: wkhtmltopdf selected",
    }


def test_chain_delegates_to_python_renderer_when_wkhtml_is_missing(tmp_path) -> None:
    with (
        patch("bilivideo.render.chain._wkhtmltoimage_path", return_value=None),
        patch(
            "bilivideo.render.chain.check_pillow_ready",
            return_value=(True, "Markdown+MathText; font=/tmp/font.ttc"),
        ),
    ):
        chain = RenderChain(output_dir=str(tmp_path), image_width=800)

    expected = Path(tmp_path) / "t.png"

    class _Renderer:
        def render(self, markdown_text: str, **kwargs):
            assert markdown_text == "# test"
            assert kwargs == {
                "base_filename": "t",
                "max_cards_per_image": 4,
                "enable_split": False,
            }
            return [expected]

    chain._renderer = _Renderer()
    assert chain.render(
        "# test",
        base_filename="t",
        max_cards_per_image=4,
        enable_split=False,
    ) == [expected]


def test_wkhtml_failure_does_not_switch_to_python(tmp_path) -> None:
    with patch(
        "bilivideo.render.chain._wkhtmltoimage_path",
        return_value="/usr/bin/wkhtmltoimage",
    ):
        chain = RenderChain(output_dir=str(tmp_path))

    class _FailingRenderer:
        def render(self, *args, **kwargs):
            raise RenderError("wkhtml failed")

    chain._renderer = _FailingRenderer()
    with pytest.raises(RenderError, match="wkhtml failed"):
        chain.render("# test", base_filename="note")
    assert chain.available_backends == ["wkhtmltopdf"]


def test_chain_propagates_partial_render_details(tmp_path) -> None:
    with (
        patch("bilivideo.render.chain._wkhtmltoimage_path", return_value=None),
        patch("bilivideo.render.chain.check_pillow_ready", return_value=(True, "ready")),
    ):
        chain = RenderChain(output_dir=str(tmp_path))

    successful = Path(tmp_path) / "note_p2.png"

    class _PartialRenderer:
        def render(self, *args, **kwargs):
            raise PartialRenderError(
                "page 1 failed",
                generated_paths=[successful],
                failed_pages=[1],
            )

    chain._renderer = _PartialRenderer()
    with pytest.raises(PartialRenderError) as exc:
        chain.render("# test", base_filename="note")

    assert exc.value.generated_paths == [successful]
    assert exc.value.failed_pages == [1]


def test_chain_reports_when_both_backends_are_unavailable(tmp_path) -> None:
    with (
        patch("bilivideo.render.chain._wkhtmltoimage_path", return_value=None),
        patch(
            "bilivideo.render.chain.check_pillow_ready",
            return_value=(False, "missing Python dependency: markdown_it"),
        ),
    ):
        chain = RenderChain(output_dir=str(tmp_path))

    assert chain.available_backends == []
    assert chain.backend_diagnostics == {
        "wkhtmltopdf": "missing wkhtmltoimage on PATH",
        "python": "unavailable: missing Python dependency: markdown_it",
    }
    with pytest.raises(RenderError, match="no image renderer available"):
        chain.render("# test", base_filename="note")


def test_chain_reports_python_fallback_ready(tmp_path) -> None:
    reason = "Markdown+MathText; font=/tmp/font.ttc"
    with (
        patch("bilivideo.render.chain._wkhtmltoimage_path", return_value=None),
        patch("bilivideo.render.chain.check_pillow_ready", return_value=(True, reason)),
    ):
        chain = RenderChain(output_dir=str(tmp_path))

    assert chain.available_backends == ["python"]
    assert chain.backend_diagnostics == {
        "wkhtmltopdf": "missing wkhtmltoimage on PATH",
        "python": f"ready {reason}",
    }
