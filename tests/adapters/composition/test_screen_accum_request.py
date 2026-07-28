"""Shared screen-accum request builder — CLI/TUI default parity."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.adapters.composition.screen_accum_request import (
    DEFAULT_SORT_BY,
    DEFAULT_TOP,
    DEFAULT_WINDOW,
    build_default_screen_accum_request,
    build_screen_accum_request,
)
from src.adapters.tui.presenters.accum_presenter import AccumPresenter


def test_defaults_match_cli_typer_baseline():
    """Lock constants to CLI flag defaults (window=7, top=20, sort=signal)."""
    assert DEFAULT_WINDOW == 7
    assert DEFAULT_TOP == 20
    assert DEFAULT_SORT_BY == "signal"


def test_default_request_shape():
    req = build_default_screen_accum_request(
        tickers=["BBRI", "BBCA"],
        universe="lq45",
    )
    assert req.tickers == ["BBRI", "BBCA"]
    assert req.universe_name == "lq45"
    assert req.window == DEFAULT_WINDOW
    assert req.top == DEFAULT_TOP
    assert req.sort_by == DEFAULT_SORT_BY
    assert req.multi is False
    assert req.windows == []
    assert req.save_enabled is False
    assert req.include_strategy_overlay is False
    assert req.min_streak == 0
    assert req.min_accum_score is None
    assert req.as_of_date is None


def test_cli_flag_passthrough():
    req = build_screen_accum_request(
        tickers=["TLKM"],
        universe_label="custom",
        universe_name=None,
        window=30,
        top=10,
        multi=True,
        windows=[7, 30],
        sort_by="score",
        strategy_name="foreign-bounce",
        save_name="shortlist",
        as_of_date=date(2026, 7, 1),
    )
    assert req.window == 30
    assert req.top == 10
    assert req.multi is True
    assert req.windows == [7, 30]
    assert req.sort_by == "score"
    assert req.include_strategy_overlay is True
    assert req.save_enabled is True
    assert req.save_name == "shortlist"
    assert req.as_of_date == date(2026, 7, 1)


def test_tui_and_cli_default_request_identical_for_same_tickers():
    """TUI cockpit open must not invent different top/sort/window than CLI defaults."""
    tickers = ["PGEO", "INDF", "BBTN"]
    tui = build_default_screen_accum_request(tickers=tickers, universe="lq45")
    cli = build_screen_accum_request(
        tickers=tickers,
        universe_label="lq45",
        universe_name="lq45",
        # explicit CLI defaults (as Typer would pass when user omits flags)
        window=7,
        min_streak=0,
        min_accum_score=None,
        min_signal_score=None,
        min_piotroski=0,
        strategy_name=None,
        include_strategy_overlay=False,
        multi=False,
        windows=[],
        top=20,
        save_name=None,
        save_enabled=False,
        vwap_only=False,
        squeeze_only=False,
        sort_by="signal",
        as_of_date=None,
    )
    assert tui == cli


def test_presenter_parity_fields_from_candidate():
    """Display mapping only reads candidate fields — no second scoring path."""
    action = SimpleNamespace(value="WATCH", short="WATCH")
    cand = SimpleNamespace(
        ticker="PGEO",
        accum_score=62.2,
        rsi=60.65,
        consecutive_streak=6,
        net_buy_ratio=0.857,
        vwap_discount_pct=-1.24,
        current_price=1020,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
        trade_setup=SimpleNamespace(action=action, rationale="x"),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(score=79, strength=SimpleNamespace(value="STRONG"))
        ),
        risk_assessment=SimpleNamespace(gate_triggered=None),
        name="PGEO",
    )
    view = AccumPresenter().present(
        SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[cand],
                window_days=DEFAULT_WINDOW,
                data_as_of={},
                applied_filters=SimpleNamespace(sort_by=DEFAULT_SORT_BY, top=DEFAULT_TOP),
            )
        )
    )
    row = view.rows[0]
    assert row.ticker == "PGEO"
    assert row.signal == "79"
    assert row.accum == "62.2"
    assert row.action == "WATCH"
    assert row.gate == "OPEN"
