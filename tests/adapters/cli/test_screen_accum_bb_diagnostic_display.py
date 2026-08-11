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
from types import SimpleNamespace

from src.adapters.cli.screen_accum_display import display_results
from src.adapters.cli.screen_accum_formatters import AccumulationDisplayConfig
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.domain.value_objects.accum_score_breakdown import (
    AccumScoreBreakdown,
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
)


def _bb_disabled_config() -> AccumulationDisplayConfig:
    return AccumulationDisplayConfig(
        enter_min_accum_score=70.0,
        watch_min_accum_score=50.0,
        coiled_spring_min_accum_score=60.0,
        coiled_spring_bb_pctile=0.05,
        accum_score_policy=SimpleNamespace(
            bb_squeeze=SimpleNamespace(
                enabled=False,
                weight=0,
                tight_pctile=0.05,
                loose_pctile=0.15,
            ),
            # The scoring-definitions panel renders every sleeve, so the fake
            # policy has to carry them all. Values are arbitrary; only the
            # bb_squeeze row is under test.
            consistency=SimpleNamespace(weight=33.3),
            streak=SimpleNamespace(weight=16.7, tau_days=3.0),
            vwap_discount=SimpleNamespace(weight=16.7, saturate_at=5.0),
            rsi_headroom=SimpleNamespace(weight=16.7, low=30.0, high=70.0, peak=50.0),
            foreign_flow_ratio=SimpleNamespace(weight=16.7, saturate_at=20.0),
            bci=SimpleNamespace(cluster_points=5.0, stable_points=2.5),
            base_enter_score=70,
            base_watch_score=50,
        ),
    )


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
        "accum_score": 58.3,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def _breakdown_with_tight_bb() -> AccumScoreBreakdown:
    return AccumScoreBreakdown(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 19),
        components=(
            ForeignFlowComponentScore("cons", 23.3, 23.3, ForeignFlowComponentStatus.AVAILABLE),
            ForeignFlowComponentScore("streak", 12.5, 12.5, ForeignFlowComponentStatus.AVAILABLE),
            ForeignFlowComponentScore("vwap", 5.0, 5.0, ForeignFlowComponentStatus.AVAILABLE),
            ForeignFlowComponentScore("rsi", 6.7, 6.7, ForeignFlowComponentStatus.AVAILABLE),
            ForeignFlowComponentScore("flow", 2.5, 2.5, ForeignFlowComponentStatus.AVAILABLE),
            ForeignFlowComponentScore("bb", None, 8.3, ForeignFlowComponentStatus.DISABLED),
            ForeignFlowComponentScore("inst", 8.3, 8.3, ForeignFlowComponentStatus.AVAILABLE),
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
    """BB must read as a diagnostic, never as scored flow points.

    Asserted against the detail view: 5cb8412b (task 07) made the default
    output compact, moving the scoring-definitions panel — which is where the
    BB%ile row lives — behind the drill-down. The BB ownership contract under
    test is unchanged; only the surface that renders it moved.
    """
    candidate = _candidate(
        bb_width_pctile=0.05,
        accum_score_breakdown=_breakdown_with_tight_bb(),
    )

    response = _response(candidate)
    display_results(
        response=response,
        candidates=response.candidates,
        universe_label="lq45",
        show_top_broker=False,
        display_config=_bb_disabled_config(),
        include_detail=True,
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
        accum_score_breakdown=_breakdown_with_tight_bb(),
    )
    d = candidate.to_dict()
    assert d["accum_score_breakdown"]["breakdown"]["bb"] is None
    assert d["bb_width_pctile"] == 0.05


def test_guide_text_states_bb_is_diagnostic_not_default_flow_score(capsys):
    from src.adapters.cli.screen_accum_display import print_column_guide

    print_column_guide()
    out = capsys.readouterr().out

    import re

    plain = re.sub(r"[─│╭╮╰╯├┤┬┴┼]", " ", out.lower())
    flat = " ".join(plain.split())
    assert "not scored in default foreign-flow score" in flat
    assert "not scored by default" in flat
    # Stale wording implying BB is part of the composite score must be gone.
    assert "BB width, and BCI into a single score" not in out
