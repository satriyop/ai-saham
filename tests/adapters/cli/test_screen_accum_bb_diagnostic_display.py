"""
Regression tests: BB ownership fix in `screen accum` foreign-flow display.

BB compression is setup-phase/trigger-readiness diagnostic (feeds
SetupPhaseDetector COMPRESSION), not foreign-flow evidence. When
bb_squeeze.enabled is false (the shipped default), the Foreign Flow Score
panel and guide text must not present BB as scored points.

Layer: Adapter (render-only, no scoring change — config drives the toggle).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.adapters.cli.screen_accum_display import display_results
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.domain.value_objects.foreign_flow_score_breakdown import ForeignFlowScoreBreakdown


def _candidate(**overrides) -> AccumulationCandidate:
    values = {
        "ticker": "BBCA",
        "window_days": 7,
        "net_buy_days": 5,
        "total_days": 7,
        "net_buy_ratio": 5 / 7,
        "total_net_value": Decimal("10000000000"),
        "consecutive_streak": 3,
        "foreign_vwap": Decimal("1030"),
        "current_price": Decimal("1000"),
        "vwap_discount_pct": 3.0,
        "rsi": 55.0,
        "trend": "SIDE",
        "foreign_flow_score": 58.3,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def _breakdown_with_tight_bb() -> ForeignFlowScoreBreakdown:
    return ForeignFlowScoreBreakdown(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 19),
        foreign_flow_score=58.3,
        breakdown=(
            ("cons", 23.3),
            ("streak", 12.5),
            ("vwap", 5.0),
            ("rsi", 6.7),
            ("flow", 2.5),
            ("bb", 0.0),  # disabled by default — must be 0.0, key still present
            ("inst", 8.3),
        ),
        max_score=100.0,
        net_buy_ratio=5 / 7,
        consecutive_streak=3,
        vwap_discount_pct=3.0,
        rsi=55.0,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.05,  # tight squeeze — still populated for diagnostics
        bci_label="CLUSTER",
        bci_tier1_count=3,
    )


def _response(candidate: AccumulationCandidate) -> AccumulationScreenResponse:
    return AccumulationScreenResponse(
        candidates=[candidate],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )


def test_bb_not_shown_as_scored_flow_points_when_disabled(capsys):
    candidate = _candidate(
        bb_width_pctile=0.05,
        foreign_flow_score_breakdown=_breakdown_with_tight_bb(),
    )

    display_results(
        response=_response(candidate),
        universe_label="lq45",
        top_n=10,
        show_top_broker=False,
        vwap_only=False,
        squeeze_only=False,
        include_explanation=False,
    )

    out = capsys.readouterr().out
    assert "BB%ile" in out
    assert "5%" in out  # bb_width_pctile still shown diagnostically
    assert "Setup compression diagnostic, not flow score" in out
    # No scored points line for the disabled BB row (would otherwise show a
    # non-zero points value like "5.0" for this tight-squeeze breakdown).
    assert "Volatility squeeze" not in out


def test_bb_width_pctile_remains_populated_in_json_dict():
    candidate = _candidate(
        bb_width_pctile=0.05,
        foreign_flow_score_breakdown=_breakdown_with_tight_bb(),
    )
    d = candidate.to_dict()
    assert d["foreign_flow_score_breakdown"]["breakdown"]["bb"] == 0.0
    assert d["bb_width_pctile"] == 0.05


def test_guide_text_states_bb_is_diagnostic_not_default_flow_score(capsys):
    from src.adapters.cli.screen_accum_display import print_column_guide

    print_column_guide()
    out = capsys.readouterr().out

    assert "not scored in default foreign-flow score" in out.lower()
    assert "not scored by default" in out.lower()
    # Stale wording implying BB is part of the composite score must be gone.
    assert "BB width, and BCI into a single score" not in out
