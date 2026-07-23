"""Persistence of Accum sector/group breadth bonus fields.

Semantic classification: OBSERVATION_SCHEMA additive payload keys
(serialization completeness). Scoring behavior unchanged. Schema version
not bumped — same precedent as additive `bci_absorption_ratio` persistence;
old rows lack keys and remain readable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.services.accumulation_sector_breadth import (
    AccumulationSectorBreadthApplier,
)


def _candidate(ticker: str, net_buy_ratio: float) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=7,
        net_buy_days=3,
        total_days=7,
        net_buy_ratio=net_buy_ratio,
        total_net_value=Decimal("1000"),
        consecutive_streak=1,
        foreign_vwap=None,
        current_price=Decimal("100"),
        vwap_discount_pct=None,
        rsi=None,
        trend="SIDE",
        accum_score=50.0,
        top_brokers=[],
        institutional_flag=False,
        bci_label="STABLE",
        bci_tier1_count=1,
    )


def test_to_dict_includes_sector_breadth_defaults_before_apply():
    payload = _candidate("BBCA", 0.5).to_dict()
    assert "sector_breadth_pct" in payload
    assert payload["sector_breadth_pct"] is None
    assert payload["sector_breadth_bonus"] == 0.0


def test_applier_persists_breadth_pct_and_bonus_in_to_dict():
    applier = AccumulationSectorBreadthApplier(
        ticker_to_group={"BBCA": "BUMN", "BBRI": "BUMN", "BMRI": "BUMN"}
    )
    candidates = [
        _candidate("BBCA", 1.0),
        _candidate("BBRI", 1.0),
        _candidate("BMRI", 0.0),
    ]
    request = AccumulationScreenRequest(
        tickers=["BBCA", "BBRI", "BMRI"],
        window_days=7,
        as_of_date=date(2026, 6, 19),
        sector_breadth_enabled=True,
        sector_breadth_threshold=0.60,
        sector_breadth_bonus_pts=10.0,
        sector_breadth_min_tickers=3,
    )

    applier.apply(candidates, request)

    # 2/3 peers net-buy → breadth ≈ 0.666… ≥ 0.60 → bonus applied to all members
    for c in candidates:
        assert c.sector_breadth_pct == pytest.approx(2 / 3)
        assert c.sector_breadth_bonus == 10.0
        assert c.accum_score == 60.0
        payload = c.to_dict()
        assert payload["sector_breadth_pct"] == round(2 / 3, 4)
        assert payload["sector_breadth_bonus"] == 10.0


def test_applier_sets_breadth_without_bonus_when_below_threshold():
    applier = AccumulationSectorBreadthApplier(
        ticker_to_group={"BBCA": "BUMN", "BBRI": "BUMN", "BMRI": "BUMN"}
    )
    candidates = [
        _candidate("BBCA", 1.0),
        _candidate("BBRI", 0.0),
        _candidate("BMRI", 0.0),
    ]
    request = AccumulationScreenRequest(
        tickers=["BBCA", "BBRI", "BMRI"],
        window_days=7,
        as_of_date=date(2026, 6, 19),
        sector_breadth_threshold=0.60,
        sector_breadth_bonus_pts=10.0,
        sector_breadth_min_tickers=3,
    )

    applier.apply(candidates, request)

    for c in candidates:
        assert c.sector_breadth_pct == pytest.approx(1 / 3)
        assert c.sector_breadth_bonus == 0.0
        assert c.accum_score == 50.0
        payload = c.to_dict()
        assert payload["sector_breadth_pct"] == round(1 / 3, 4)
        assert payload["sector_breadth_bonus"] == 0.0
