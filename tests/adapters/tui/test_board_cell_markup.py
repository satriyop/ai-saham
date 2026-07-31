"""Accum board chip elevation — present-only cell markup."""

from __future__ import annotations

from types import SimpleNamespace

from rich.text import Text

from src.adapters.tui.board_cell_markup import (
    format_accum_board_cells,
    format_action_cell,
    format_gate_cell,
    format_signal_cell,
    format_triage_markup,
    signal_heat_band,
)


def test_signal_heat_bands():
    assert signal_heat_band("91") == "hi"
    assert signal_heat_band("84") == "hi"
    assert signal_heat_band("78") == "mid"
    assert signal_heat_band("68") == "lo"
    assert signal_heat_band("—") == "na"


def test_action_chip_styles_present():
    enter = format_action_cell("ENTER")
    watch = format_action_cell("WATCH")
    avoid = format_action_cell("AVOID")
    assert isinstance(enter, Text)
    assert "ENTER" in enter.plain
    assert "WATCH" in watch.plain
    assert "AVOID" in avoid.plain
    # Styles applied (not plain monochrome)
    assert enter.spans or str(enter.style)
    # OpenCode semantic greens/ambers/reds (not journey night-ink palette)
    assert "#6fbf8a" in enter.markup or "6fbf8a" in repr(enter)
    assert "#d4b06a" in watch.markup or "d4b06a" in repr(watch)
    assert "#c97a72" in avoid.markup or "c97a72" in repr(avoid)
    # No opaque cell backgrounds — they punch black holes through peach cursor
    for cell in (enter, watch, avoid):
        blob = cell.markup + repr(cell)
        assert " on " not in blob.lower() or "on #" not in blob
        assert "#121a14" not in blob and "#1a1810" not in blob and "#1a1212" not in blob


def test_phase_cell_no_opaque_background():
    from src.adapters.tui.board_cell_markup import format_phase_cell

    phase = format_phase_cell("COMPRESS")
    assert "COMPRESS" in phase.plain
    blob = phase.markup + repr(phase)
    assert "#141414" not in blob
    assert " on " not in blob


def test_gate_and_signal_markup():
    assert "OPEN" in format_gate_cell("OPEN").plain
    assert "BLOCK" in format_gate_cell("BLOCK").plain
    hi = format_signal_cell("91")
    lo = format_signal_cell("65")
    assert hi.plain == "91"
    assert lo.plain == "65"


def test_format_accum_board_cells_order_and_values():
    row = SimpleNamespace(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        phase="COMPRESS",
        streak="2",
        rsi="48",
        net_pct="0.5",
        disc_pct="0.2",
        price="6275",
        gate="OPEN",
    )
    cells = format_accum_board_cells(row)
    assert len(cells) == 11
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert plains[0] == "BBCA"
    assert plains[1] == "84"
    assert plains[2] == "48.2"
    assert "WATCH" in plains[3]
    assert "COMPRESS" in plains[4]
    assert plains[5] == "2"
    assert "OPEN" in plains[10]


def test_triage_markup_colors_actions():
    s = format_triage_markup("12 names · Action: ENTER 2, WATCH 7, AVOID 3 · Gate: OPEN 9")
    assert "ENTER" in s and "WATCH" in s and "AVOID" in s
    assert "[#" in s  # textual/rich color tags


def test_accum_board_chip_cells_paint_contract():
    """Action/signal/gate chip cells from pure markup (what board table paints)."""
    row = SimpleNamespace(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        phase="COMPRESS",
        streak="2",
        rsi="48",
        net_pct="0.5",
        disc_pct="0.2",
        price="6275",
        gate="OPEN",
    )
    cells = format_accum_board_cells(row)
    plains = [c.plain if isinstance(c, Text) else str(c) for c in cells]
    assert "WATCH" in plains[3]
    assert "84" in plains[1]
    assert "OPEN" in plains[10]
    triage = format_triage_markup("12 names · Action: ENTER 2, WATCH 7, AVOID 3 · Gate: OPEN 9")
    assert "WATCH" in triage
