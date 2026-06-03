"""Small persistent runtime-state store.

Commands such as `/识别开关` mutate state at runtime. Keeping those values in
their own JSON file avoids pretending they changed the static AstrBot config.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .logging import get_logger

logger = get_logger("BiliVideo/RuntimeState")


class RuntimeState:
    """File-backed runtime state with best-effort atomic writes."""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / "runtime_state.json"
        self._data: dict[str, Any] = {}
        self._load()

    def get_bool(self, key: str) -> bool | None:
        value = self._data.get(key)
        return value if isinstance(value, bool) else None

    def set_bool(self, key: str, value: bool) -> None:
        self._data[key] = value
        self._persist()

    def get_str(self, key: str) -> str | None:
        value = self._data.get(key)
        return value if isinstance(value, str) else None

    def set_str(self, key: str, value: str) -> None:
        self._data[key] = value
        self._persist()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"runtime state load failed ({self._path}): {exc}")
            return
        if isinstance(payload, dict):
            self._data = payload

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                delete=False,
                dir=str(self._path.parent),
                prefix=".runtime_state.",
                suffix=".tmp",
            ) as tmp:
                json.dump(self._data, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)
            temp_path.replace(self._path)
        except OSError as exc:
            logger.warning(f"runtime state persist failed: {exc}")
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
