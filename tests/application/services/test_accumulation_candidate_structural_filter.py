"""Tests for AccumulationCandidateStructuralFilter."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.services.accumulation_candidate_structural_filter import (
    AccumulationCandidateStructuralFilter,
)
from src.domain.value_objects.company_fundamentals import CompanyFundamentals


def _candidate() -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker="BBCA",
        window_days=7,
        net_buy_days=4,
        total_days=5,
        net_buy_ratio=0.8,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=50.0,
        top_brokers=None,
        institutional_flag=False,
    )


def _request(
    min_market_cap_idr: int = 0,
    min_piotroski: int = 0,
    as_of_date: date | None = None,
) -> AccumulationScreenRequest:
    return AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        min_market_cap_idr=min_market_cap_idr,
        min_piotroski=min_piotroski,
        as_of_date=as_of_date,
    )


def _fundamentals_provider(
    market_cap_idr: int | None = 500_000_000_000,
    piotroski_score: int | None = 6,
) -> MagicMock:
    prov = MagicMock()
    if market_cap_idr is not None or piotroski_score is not None:
        prov.get_fundamentals.return_value = CompanyFundamentals(
            ticker="BBCA",
            pe_ratio_ttm=12.0,
            roe_ttm=15.0,
            net_profit_margin=12.0,
            revenue_yoy_growth=8.0,
            piotroski_f_score=piotroski_score,
            dividend_yield=2.0,
            week52_high=1200.0,
            week52_low=800.0,
            near_52w_high_rank=50.0,
            market_cap_idr=market_cap_idr,
        )
    else:
        prov.get_fundamentals.return_value = None
    return prov


def test_no_fundamentals_fetch_when_both_gates_disabled():
    """When both min_market_cap_idr and min_piotroski are 0, no fetch occurs."""
    provider = MagicMock()
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=provider)
    result = filter_obj.apply(_candidate(), _request())

    assert result.fundamentals_fetched is False
    assert result.rejected is False
    assert result.screen_result is None
    provider.get_fundamentals.assert_not_called()


def test_fetch_when_market_cap_gate_enabled():
    """Provider is called when min_market_cap_idr > 0."""
    provider = _fundamentals_provider(market_cap_idr=1_000_000_000_000)
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=provider)
    result = filter_obj.apply(_candidate(), _request(min_market_cap_idr=500_000_000_000))

    provider.get_fundamentals.assert_called_once()
    assert result.fundamentals_fetched is True
    assert result.rejected is False


def test_none_fundamentals_when_missing_market_cap_rejected_as_flow():
    """None fundamentals with active market-cap gate rejects."""
    provider = _fundamentals_provider(market_cap_idr=None, piotroski_score=6)
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=provider)
    result = filter_obj.apply(_candidate(), _request(min_market_cap_idr=100_000_000_000))

    assert result.rejected is True
    assert result.screen_result == "rejected_flow"


def test_low_market_cap_rejects_as_flow():
    """Candidate below market-cap floor is rejected."""
    provider = _fundamentals_provider(market_cap_idr=50_000_000_000)
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=provider)
    result = filter_obj.apply(_candidate(), _request(min_market_cap_idr=100_000_000_000))

    assert result.rejected is True
    assert result.screen_result == "rejected_flow"


def test_missing_piotroski_rejects_as_flow():
    """None Piotroski with active piotroski gate rejects."""
    provider = _fundamentals_provider(market_cap_idr=1_000_000_000_000, piotroski_score=None)
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=provider)
    result = filter_obj.apply(_candidate(), _request(min_piotroski=5))

    assert result.rejected is True
    assert result.screen_result == "rejected_flow"


def test_low_piotroski_rejects_as_flow():
    """Candidate below Piotroski floor is rejected."""
    provider = _fundamentals_provider(piotroski_score=3)
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=provider)
    result = filter_obj.apply(_candidate(), _request(min_piotroski=5))

    assert result.rejected is True
    assert result.screen_result == "rejected_flow"


def test_accepted_candidate_returns_fundamentals_fetched_true():
    """When fundamentals are fetched and all gates pass, fundamentals_fetched=True."""
    provider = _fundamentals_provider(market_cap_idr=500_000_000_000, piotroski_score=6)
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=provider)
    result = filter_obj.apply(
        _candidate(),
        _request(min_market_cap_idr=100_000_000_000, min_piotroski=5),
    )

    assert result.fundamentals_fetched is True
    assert result.rejected is False
    assert result.screen_result is None
    assert result.candidate.fundamentals is not None


def test_no_provider_no_fetch():
    """When provider is None, no fetch occurs even with gates enabled."""
    filter_obj = AccumulationCandidateStructuralFilter(fundamentals_provider=None)
    result = filter_obj.apply(
        _candidate(),
        _request(min_market_cap_idr=100_000_000_000),
    )

    assert result.fundamentals_fetched is False
    assert result.rejected is False
    assert result.screen_result is None
