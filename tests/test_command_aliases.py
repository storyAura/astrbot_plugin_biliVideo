"""Static checks for short English command aliases."""

from __future__ import annotations

import ast
import re
from pathlib import Path

SHORT_ALIAS_RE = re.compile(r"^[a-z][a-z0-9]{1,7}$")


def _literal_command_names() -> list[tuple[str, set[str]]]:
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    commands: list[tuple[str, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "command"
                and isinstance(func.value, ast.Name)
                and func.value.id == "filter"
            ):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            command = decorator.args[0].value
            aliases: set[str] = set()
            for keyword in decorator.keywords:
                if keyword.arg != "alias":
                    continue
                value = ast.literal_eval(keyword.value)
                if isinstance(value, str):
                    aliases.add(value)
                else:
                    aliases.update(item for item in value if isinstance(item, str))
            commands.append((command, aliases))
    return commands


def test_each_command_has_short_english_alias() -> None:
    commands = _literal_command_names()
    assert len(commands) >= 17
    missing: list[str] = []
    for command, aliases in commands:
        names = {command, *aliases}
        if not any(SHORT_ALIAS_RE.fullmatch(name) for name in names):
            missing.append(command)

    assert missing == []


def test_commands_and_aliases_do_not_conflict() -> None:
    seen: dict[str, str] = {}
    conflicts: list[str] = []
    for command, aliases in _literal_command_names():
        for name in {command, *aliases}:
            owner = seen.setdefault(name, command)
            if owner != command:
                conflicts.append(f"{name}: {owner} / {command}")

    assert conflicts == []
