"""
Baseline capture for the current AssessSignalUseCase composite scoring.

Phase 0 evidence: freezes the current flat-weighted output for representative
SignalContext cases so Phase 4 (renormalization) can be compared against a known
reference. These are comparison evidence, NOT frozen behavior requirements — if
a deliberate scoring change lands, the golden values here are expected to move.

Golden scores were captured from the current engine on 2026-07-03 with default
weights. Note: the "bandar_and_flow_only" case scores 70 (STRONG), not ~50 — two
high factors at weight 0.20 each pull the flat average well above neutral even
with four neutral-filled factors. This asymmetry is exactly what Phase 4's
renormalization is meant to expose.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.application.use_case.assess_signal_use_case import (
    _DEFAULT_WEIGHTS,
    AssessSignalRequest,
    AssessSignalUseCase,
)
from src.domain.value_objects.signal_assessment import SignalContext

SNAPSHOT = date(2026, 7, 3)

BASELINE_CASES = [
    {
        "name": "all_factors_present_strong",
        "context": SignalContext(
            ticker="TEST",
            snapshot_date=SNAPSHOT,
            bandar_broad_score=6,
            bandar_max_range=6,
            foreign_flow_quality=0.9,
            insider_net_buy_ratio=0.8,
            seasonality_win_rate=75.0,
            seasonality_avg_return_pct=2.5,
            analyst_buy_pct=0.85,
            analyst_upside_pct=25.0,
            forward_pe=12.0,
        ),
        # Score pinned at 89 from Phase 0 golden capture (2026-07-03).
        # Breakdown: bandar=100, foreign=90, insider=90, seasonal=75, analyst=84.33, pe=87.
        # Flat weighted: round(0.20*100 + 0.20*90 + 0.20*90 + 0.15*75 + 0.15*84.33 + 0.10*87) = 89.
        "expected_score": 89,
        "expected_strength": "STRONG",
    },
    {
        "name": "all_factors_missing_neutral",
        "context": SignalContext(ticker="TEST", snapshot_date=SNAPSHOT),
        "expected_score": 50,
        "expected_strength": "MODERATE",
    },
    {
        "name": "bandar_and_flow_only",
        "context": SignalContext(
            ticker="TEST",
            snapshot_date=SNAPSHOT,
            bandar_broad_score=6,
            bandar_max_range=6,
            foreign_flow_quality=1.0,
        ),
        # Two factors max (100) at 0.20 weight each + four neutral (50) fills.
        # 0.20*100*2 + (0.20+0.15+0.15+0.10)*50 = 40 + 30 = 70.
        "expected_score": 70,
        "expected_strength": "STRONG",
    },
]


def _score(context: SignalContext):
    return (
        AssessSignalUseCase(weights=dict(_DEFAULT_WEIGHTS))
        .execute(AssessSignalRequest(ticker=context.ticker, signal_context=context))
        .assessment
    )


@pytest.mark.parametrize("case", BASELINE_CASES, ids=[c["name"] for c in BASELINE_CASES])
def test_signal_baseline(case):
    assessment = _score(case["context"])

    if "expected_score" in case:
        assert assessment.score == case["expected_score"], (
            f"{case['name']}: score {assessment.score} != {case['expected_score']}"
        )
    assert assessment.strength.value == case["expected_strength"]
