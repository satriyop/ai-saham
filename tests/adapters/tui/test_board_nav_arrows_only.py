"""Board/list navigation is arrows only — not vim j/k (design lock)."""

from __future__ import annotations

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.screens.help import HELP_BODY


def test_cockpit_bindings_use_arrows_not_jk_for_cursor():
    keys = {b.key for b in CockpitApp.BINDINGS}
    assert "up" in keys and "down" in keys
    assert "j" not in keys
    assert "k" not in keys
    # Cursor actions still exist; only bound to arrows
    assert any(b.action == "cursor_down" for b in CockpitApp.BINDINGS)
    assert any(b.action == "cursor_up" for b in CockpitApp.BINDINGS)


def test_help_copy_arrows_only_not_vim_jk():
    assert "↑↓" in HELP_BODY
    assert "j/k" in HELP_BODY or "not j/k" in HELP_BODY
    assert "↑↓ j k" not in HELP_BODY
