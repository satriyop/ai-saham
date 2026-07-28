"""Parity: one field extractor for CLI core cells and TUI board rows."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from src.adapters.composition.screen_accum_request import (
    DEFAULT_SORT_BY,
    DEFAULT_TOP,
    DEFAULT_WINDOW,
    build_default_screen_accum_request,
    build_screen_accum_request,
)
from src.adapters.shared.screen_accum_board_fields import (
    BOARD_COLUMN_LABELS,
    extract_screen_accum_board_fields,
)
from src.adapters.tui.presenters.accum_presenter import AccumPresenter


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(
        ticker="PGEO",
        accum_score=62.2,
        rsi=Decimal("60.65"),
        consecutive_streak=6,
        net_buy_ratio=0.8571428571428571,
        vwap_discount_pct=-1.2441176470588236,
        current_price=Decimal("1020"),
        setup_phase=SimpleNamespace(
            current_phase=SimpleNamespace(value="ACCUMULATION"),
        ),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(score=79),
        ),
        risk_assessment=SimpleNamespace(gate_triggered=None),
        name="PGEO Corp",
    )


def test_board_column_labels_are_adr043():
    assert "Signal" in BOARD_COLUMN_LABELS
    assert "Accum" in BOARD_COLUMN_LABELS
    assert BOARD_COLUMN_LABELS.index("Signal") < BOARD_COLUMN_LABELS.index("Accum")


def test_extract_matches_cli_core_semantics():
    """Same raw values CLI action table would print for Signal/Accum/Action/Gate/Price."""
    c = _candidate()
    f = extract_screen_accum_board_fields(c, phase_style="short")
    # CLI: int signal score, accum 1 decimal, action.short, OPEN if no gate, price int
    assert f.signal_score == 79
    assert f.signal == "79"
    assert f.accum_score == 62.2
    assert f.accum == "62.2"
    assert f.action_value == "WATCH"
    assert f.action == "WATCH"
    assert f.gate == "OPEN"
    assert f.gate_blocked is False
    assert f.price == "1,020"
    assert f.price_value == 1020.0
    assert f.disc_pct == "-1.2%"
    assert f.streak == "6"
    assert f.net_pct == "86%"
    assert f.phase == "ACCUM"  # short style for dense board
    full = extract_screen_accum_board_fields(c, phase_style="full")
    assert full.phase == "ACCUMULATION"  # CLI-style full label


def test_tui_presenter_uses_shared_extractor():
    c = _candidate()
    f = extract_screen_accum_board_fields(c, phase_style="short")
    view = AccumPresenter().present(
        SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[c],
                window_days=DEFAULT_WINDOW,
                data_as_of={},
                applied_filters=SimpleNamespace(sort_by=DEFAULT_SORT_BY, top=DEFAULT_TOP),
            )
        )
    )
    row = view.rows[0]
    assert row.ticker == f.ticker
    assert row.signal == f.signal
    assert row.accum == f.accum
    assert row.action == f.action
    assert row.phase == f.phase
    assert row.streak == f.streak
    assert row.rsi == f.rsi
    assert row.net_pct == f.net_pct
    assert row.disc_pct == f.disc_pct
    assert row.price == f.price
    assert row.gate == f.gate
    assert view.columns == BOARD_COLUMN_LABELS


def test_default_request_is_cli_default_job():
    """TUI open and bare CLI defaults are one request identity."""
    tickers = ["BBRI", "BBCA"]
    tui = build_default_screen_accum_request(tickers=tickers, universe="lq45")
    cli = build_screen_accum_request(
        tickers=tickers,
        universe_label="lq45",
        universe_name="lq45",
        window=7,
        top=20,
        sort_by="signal",
    )
    assert tui == cli
    assert tui.window == DEFAULT_WINDOW
    assert tui.top == DEFAULT_TOP
    assert tui.sort_by == DEFAULT_SORT_BY
