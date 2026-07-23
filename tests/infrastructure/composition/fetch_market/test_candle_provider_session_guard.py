"""Root-cause guard: candle-provider selection must not treat a non-Stockbit
broker provider as a Stockbit session.

Regression for the crash
    AttributeError: 'IdxBrokerDataProvider' object has no attribute 'api_client'
seen when refreshing a ticker with no authenticated Stockbit session.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.application.use_case.resolve_candle_provider_policy_use_case import (
    CandleProviderKind,
    ResolveCandleProviderPolicyRequest,
    ResolveCandleProviderPolicyUseCase,
)
from src.infrastructure.composition.fetch_market.fetch_market_candle_refresh import (
    broker_provider_can_fetch_candles,
)
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider


def test_idx_fallback_is_not_a_candle_capable_session():
    # The IDX broker provider has no api_client; it cannot serve candles.
    assert broker_provider_can_fetch_candles(IdxBrokerDataProvider()) is False
    assert broker_provider_can_fetch_candles(None) is False
    # A Stockbit session (exposes api_client) is candle-capable.
    assert broker_provider_can_fetch_candles(SimpleNamespace(api_client=object())) is True


def test_idx_only_refresh_yields_clean_error_not_stockbit_historical():
    # With the honest has_broker_session, a standard IDX ticker whose only broker
    # provider is the IDX fallback resolves to a clean "session required" error
    # instead of STOCKBIT_HISTORICAL (which would then crash on .api_client).
    decision = ResolveCandleProviderPolicyUseCase().execute(
        ResolveCandleProviderPolicyRequest(
            ticker="BBRI",
            non_idx_tickers=frozenset(),
            requested_provider_name="stockbit",
            has_broker_session=broker_provider_can_fetch_candles(IdxBrokerDataProvider()),
        )
    )
    assert decision.provider_kind is None
    assert decision.error is not None
    assert decision.provider_kind is not CandleProviderKind.STOCKBIT_HISTORICAL
