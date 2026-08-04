"""Unit tests for ViewTickerFundamentalsTrendUseCase (EPS series + latest + forward)."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.application.use_case.view_ticker_fundamentals_trend_use_case import (
    ViewTickerFundamentalsTrendRequest,
    ViewTickerFundamentalsTrendUseCase,
    eps_trend_direction,
)
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.earnings_record import EarningsRecord
from src.domain.value_objects.forward_estimates import ForwardEstimates

pytestmark = pytest.mark.agent


def _earn(year: int, q: int, eps: float, yoy: float | None = None) -> EarningsRecord:
    return EarningsRecord(
        ticker="BBCA",
        year=year,
        quarter=q,
        eps_actual=eps,
        eps_estimate=eps * 0.95,
        eps_surprise_pct=5.0,
        eps_yoy_change=yoy,
        eps_prev_year=eps - (yoy or 0),
        fetched_at=datetime(2026, 1, 1),
    )


class _Source:
    def __init__(self, earnings=None, fund=None, forward=None) -> None:
        self.earnings = earnings or []
        self.fund = fund
        self.forward = forward

    def get_earnings_history(self, ticker: str, quarters: int):
        return list(self.earnings)[:quarters]

    def get_fundamentals(self, ticker: str):
        return self.fund

    def get_forward_estimates(self, ticker: str):
        return self.forward


def test_happy_path_eps_series_and_latest() -> None:
    # newest first
    earnings = [
        _earn(2026, 1, 120.0, 10.0),
        _earn(2025, 4, 110.0, 5.0),
        _earn(2025, 3, 100.0, 0.0),
        _earn(2025, 2, 90.0, -5.0),
    ]
    fund = CompanyFundamentals(
        ticker="BBCA",
        pe_ratio_ttm=15.0,
        roe_ttm=18.0,
        net_profit_margin=20.0,
        revenue_yoy_growth=8.0,
        piotroski_f_score=7,
        dividend_yield=2.0,
        week52_high=None,
        week52_low=None,
        near_52w_high_rank=None,
        pbv=2.5,
    )
    fwd = ForwardEstimates.compute("BBCA", 130.0, 1e12, 1000.0)
    uc = ViewTickerFundamentalsTrendUseCase(_Source(earnings, fund, fwd))
    result = uc.execute(ViewTickerFundamentalsTrendRequest("bbca", quarters=4))
    assert result is not None
    assert len(result.quarters) == 4
    assert result.quarters[0].period_label == "Q1 2026"
    assert result.eps_trend_direction == "rising"
    assert result.latest_fundamentals is not None
    assert result.latest_fundamentals.piotroski_f_score == 7
    assert result.forward is not None
    assert result.forward.forward_eps_1y == 130.0
    assert result.warnings == ()
    assert not hasattr(result, "quality_score")


def test_partial_when_only_fundamentals() -> None:
    fund = CompanyFundamentals(
        ticker="BBCA",
        pe_ratio_ttm=12.0,
        roe_ttm=10.0,
        net_profit_margin=5.0,
        revenue_yoy_growth=None,
        piotroski_f_score=5,
        dividend_yield=None,
        week52_high=None,
        week52_low=None,
        near_52w_high_rank=None,
    )
    uc = ViewTickerFundamentalsTrendUseCase(_Source([], fund, None))
    result = uc.execute(ViewTickerFundamentalsTrendRequest("BBCA", quarters=4))
    assert result is not None
    assert result.quarters == ()
    assert "EARNINGS_HISTORY_UNAVAILABLE" in result.warnings
    assert "FORWARD_ESTIMATES_UNAVAILABLE" in result.warnings


def test_unavailable_when_all_missing() -> None:
    uc = ViewTickerFundamentalsTrendUseCase(_Source())
    assert uc.execute(ViewTickerFundamentalsTrendRequest("BBCA")) is None


def test_eps_trend_direction_chrono() -> None:
    rising = [_earn(2025, 1, 50), _earn(2025, 2, 60), _earn(2025, 3, 80), _earn(2025, 4, 100)]
    # newest first
    newest_first = list(reversed(rising))
    assert eps_trend_direction(newest_first) == "rising"
    assert eps_trend_direction(list(reversed(rising))) == "rising"
