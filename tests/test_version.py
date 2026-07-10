"""Version single-sourcing: metadata.yaml drives `bilivideo.__version__`."""

from __future__ import annotations

import re
from pathlib import Path

import bilivideo

_ROOT = Path(__file__).resolve().parents[1]


def test_version_comes_from_metadata() -> None:
    meta = (_ROOT / "metadata.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*v?(\S+)\s*$", meta, flags=re.MULTILINE)
    assert match is not None, "metadata.yaml must declare a version"
    assert bilivideo.__version__ == match.group(1)


def test_version_looks_like_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+.].*)?", bilivideo.__version__)


def test_pyproject_does_not_hardcode_version() -> None:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject
