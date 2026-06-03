"""Runtime-state persistence tests."""

from __future__ import annotations

from bilivideo.core.runtime_state import RuntimeState


def test_runtime_state_persists_bool(tmp_path) -> None:
    state = RuntimeState(tmp_path)
    state.set_bool("enable_miniapp_detect", True)

    reloaded = RuntimeState(tmp_path)

    assert reloaded.get_bool("enable_miniapp_detect") is True
