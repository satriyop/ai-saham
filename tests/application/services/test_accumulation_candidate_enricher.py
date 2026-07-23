"""Tests for AccumulationCandidateEnricher."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationDerivedFeaturePolicy,
    AccumulationScreenRequest,
)
from src.application.services.accumulation_candidate_enricher import (
    AccumulationCandidateEnricher,
)
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.forward_estimates import ForwardEstimates


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
        accum_score=0.0,
        top_brokers=None,
        institutional_flag=False,
        bci_label="STABLE",
        bci_tier1_count=2,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.3,
    )


def _request(as_of_date: date | None = None) -> AccumulationScreenRequest:
    return AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        as_of_date=as_of_date,
    )


def _make_enricher(
    fundamentals_provider=None,
    forward_estimates_provider=None,
    insider_provider=None,
) -> AccumulationCandidateEnricher:
    return AccumulationCandidateEnricher(
        fundamentals_provider=fundamentals_provider,
        forward_estimates_provider=forward_estimates_provider,
        insider_provider=insider_provider,
        derived_features=AccumulationDerivedFeaturePolicy(),
    )


def test_does_not_fetch_fundamentals_when_already_fetched():
    """When fundamentals_fetched=True, enricher skips fundamentals fetch."""
    fundamentals_provider = MagicMock()
    enricher = _make_enricher(fundamentals_provider=fundamentals_provider)

    candidate = _candidate()
    candidate.fundamentals = MagicMock()
    result = enricher.enrich(
        candidate,
        request=_request(),
        as_of_date=date.today(),
        fundamentals_fetched=True,
    )

    fundamentals_provider.get_fundamentals.assert_not_called()
    assert result.candidate.fundamentals is not None


def test_fetches_fundamentals_when_not_already_fetched():
    """When fundamentals_fetched=False, enricher fetches fundamentals."""
    fundamentals_provider = MagicMock()
    fundamentals_provider.get_fundamentals.return_value = CompanyFundamentals(
        ticker="BBCA",
        pe_ratio_ttm=12.0,
        roe_ttm=15.0,
        net_profit_margin=12.0,
        revenue_yoy_growth=8.0,
        piotroski_f_score=6,
        dividend_yield=2.0,
        week52_high=1200.0,
        week52_low=800.0,
        near_52w_high_rank=50.0,
    )
    enricher = _make_enricher(fundamentals_provider=fundamentals_provider)

    candidate = _candidate()
    result = enricher.enrich(
        candidate,
        request=_request(),
        as_of_date=date.today(),
        fundamentals_fetched=False,
    )

    fundamentals_provider.get_fundamentals.assert_called_once()
    assert result.candidate.fundamentals is not None


def test_forward_pe_derived_from_current_price_when_missing():
    """Forward P/E is derived from current price when forward_pe is None."""
    forward_provider = MagicMock()
    forward_provider.get_forward_estimates.return_value = ForwardEstimates(
        ticker="BBCA",
        forward_eps_1y=10.0,
        revenue_forward_1y=None,
        current_price=None,
        forward_pe=None,
    )
    enricher = _make_enricher(forward_estimates_provider=forward_provider)

    candidate = _candidate()
    candidate.current_price = Decimal("100")

    result = enricher.enrich(
        candidate,
        request=_request(),
        as_of_date=date.today(),
        fundamentals_fetched=False,
    )

    assert result.candidate.forward_estimates is not None
    assert result.candidate.forward_estimates.forward_pe == 10.0


def test_insider_net_buy_ratio_none_converted_to_zero():
    """Insider net-buy ratio None from provider converts to 0.0."""
    insider_provider = MagicMock()
    insider_provider.get_insider_transactions.return_value = []

    enricher = _make_enricher(insider_provider=insider_provider)

    result = enricher.enrich(
        _candidate(),
        request=_request(),
        as_of_date=date.today(),
        fundamentals_fetched=False,
    )

    assert result.insider_net_buy_ratio == 0.0
