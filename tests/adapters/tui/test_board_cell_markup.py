"""Accum board chip elevation — present-only cell markup."""

from __future__ import annotations

import asyncio
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
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter


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


def test_cockpit_accum_table_paints_chip_cells():
    c = SimpleNamespace(
        ticker="BBCA",
        accum_score=48.2,
        rsi=48.0,
        consecutive_streak=2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.2,
        current_price=6275,
        name="BBCA",
        latest_candle_date=None,
        latest_broker_date=None,
        freshness=None,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="COMPRESSION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            signal_score=84,
            signal_strength=SimpleNamespace(value="MODERATE"),
            rationale="ok",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(
                score=84,
                strength=SimpleNamespace(value="MODERATE"),
                entry_quality=SimpleNamespace(value="WATCH"),
                signal_authority_coverage=0.9,
                breakdown=None,
                decision_constraints=None,
            ),
            setup_readiness=None,
            coverage_warning=None,
            signal_authority_coverage=0.9,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(),
    )
    result = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-29"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: result,
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            app._on_accum_payload(result)
            await pilot.pause(0.05)
            assert app._stage == "accum"
            table = app.query_one("#board-table")
            assert table.display is True
            # Cell content via coordinate — Action column index 3
            from textual.widgets import DataTable

            dt = app.query_one("#board-table", DataTable)
            # row 0, col Action
            cell = dt.get_cell_at((0, 3))
            plain = cell.plain if isinstance(cell, Text) else str(cell)
            assert "WATCH" in plain
            sig = dt.get_cell_at((0, 1))
            sig_plain = sig.plain if isinstance(sig, Text) else str(sig)
            assert "84" in sig_plain
            gate = dt.get_cell_at((0, 10))
            gate_plain = gate.plain if isinstance(gate, Text) else str(gate)
            assert "OPEN" in gate_plain
            # Meta strip includes triage when summary present
            meta = str(app.query_one("#view-meta").render())
            assert "WATCH" in meta or "names" in meta.lower() or "Action" in meta

    asyncio.run(scenario())
