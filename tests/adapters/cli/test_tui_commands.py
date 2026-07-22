"""Tests for the lazy optional TUI CLI boundary."""

from __future__ import annotations

import subprocess
import sys

import pytest
from typer.testing import CliRunner

from src.adapters.cli import tui_commands
from src.adapters.cli.main import app

runner = CliRunner()


def _module_not_found(name: str) -> ModuleNotFoundError:
    return ModuleNotFoundError(f"No module named {name!r}", name=name)


def test_root_help_lists_tui_without_importing_textual():
    script = """
import sys
from src.adapters.cli.main import app
assert 'textual' not in sys.modules
assert 'src.adapters.tui.main' not in sys.modules
print(app.info.name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "saham"

    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "tui" in help_result.stdout


def test_missing_textual_has_exact_message_and_exit_code(monkeypatch):
    def missing_runner():
        raise _module_not_found("textual")

    monkeypatch.setattr(tui_commands, "_load_tui_runner", missing_runner)

    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 1
    assert result.stderr.strip() == tui_commands.MISSING_TUI_EXTRA_MESSAGE


def test_unrelated_module_not_found_propagates(monkeypatch):
    failure = _module_not_found("unrelated_transitive_dependency")

    def missing_runner():
        raise failure

    monkeypatch.setattr(tui_commands, "_load_tui_runner", missing_runner)

    with pytest.raises(ModuleNotFoundError) as caught:
        tui_commands.tui()

    assert caught.value is failure


def test_installed_tui_runner_is_invoked_once(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        tui_commands,
        "_load_tui_runner",
        lambda: lambda: calls.append("run"),
    )

    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 0
    assert calls == ["run"]
