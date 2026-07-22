"""Static packaging contracts for the optional TUI dependency."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_textual_is_closed_range_optional_dependency_only():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert not any(item.startswith("textual") for item in project["dependencies"])
    assert project["optional-dependencies"]["tui"] == ["textual>=8.2,<9"]


def test_lockfile_declares_tui_extra_and_locked_textual_range():
    lockfile = Path("uv.lock").read_text(encoding="utf-8")

    assert 'tui = [\n    { name = "textual" },\n]' in lockfile
    assert 'name = "textual", marker = "extra == \'tui\'", specifier = ">=8.2,<9"' in lockfile
