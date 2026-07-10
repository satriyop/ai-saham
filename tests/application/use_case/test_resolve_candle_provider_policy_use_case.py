"""Tests for ResolveCandleProviderPolicyUseCase — pure candle provider selection."""

from src.application.use_case.resolve_candle_provider_policy_use_case import (
    STOCKBIT_SESSION_REQUIRED_ERROR,
    CandleProviderKind,
    ResolveCandleProviderPolicyRequest,
    ResolveCandleProviderPolicyUseCase,
)

USE_CASE = ResolveCandleProviderPolicyUseCase()


def test_non_idx_ticker_always_uses_yahoo():
    response = USE_CASE.execute(
        ResolveCandleProviderPolicyRequest(
            ticker="^VIX",
            non_idx_tickers=frozenset({"^VIX", "EIDO"}),
            requested_provider_name="idx",
            has_broker_session=True,
        )
    )
    assert response.provider_kind == CandleProviderKind.YAHOO
    assert response.error is None


def test_benchmark_ticker_uses_stockbit_when_session_available():
    response = USE_CASE.execute(
        ResolveCandleProviderPolicyRequest(
            ticker="IHSG",
            non_idx_tickers=frozenset(),
            requested_provider_name="yahoo",
            has_broker_session=True,
        )
    )
    assert response.provider_kind == CandleProviderKind.STOCKBIT_HISTORICAL


def test_benchmark_ticker_falls_back_to_yahoo_without_session():
    response = USE_CASE.execute(
        ResolveCandleProviderPolicyRequest(
            ticker="IHSG",
            non_idx_tickers=frozenset(),
            requested_provider_name="yahoo",
            has_broker_session=False,
        )
    )
    assert response.provider_kind == CandleProviderKind.YAHOO


def test_explicit_idx_provider_choice_wins_for_regular_ticker():
    response = USE_CASE.execute(
        ResolveCandleProviderPolicyRequest(
            ticker="BBCA",
            non_idx_tickers=frozenset(),
            requested_provider_name="idx",
            has_broker_session=False,
        )
    )
    assert response.provider_kind == CandleProviderKind.IDX_MARKET


def test_regular_idx_ticker_requires_stockbit_session():
    response = USE_CASE.execute(
        ResolveCandleProviderPolicyRequest(
            ticker="BBCA",
            non_idx_tickers=frozenset(),
            requested_provider_name="yahoo",
            has_broker_session=False,
        )
    )
    assert response.provider_kind is None
    assert response.error == STOCKBIT_SESSION_REQUIRED_ERROR


def test_regular_idx_ticker_uses_stockbit_with_session():
    response = USE_CASE.execute(
        ResolveCandleProviderPolicyRequest(
            ticker="BBCA",
            non_idx_tickers=frozenset(),
            requested_provider_name="yahoo",
            has_broker_session=True,
        )
    )
    assert response.provider_kind == CandleProviderKind.STOCKBIT_HISTORICAL
    assert response.error is None
