from src.application.services.fetch_market_provider_precondition import (
    FetchMarketProviderPrecondition,
    FetchMarketProviderPreconditionRequest,
)
from src.application.use_case.resolve_candle_provider_policy_use_case import (
    STOCKBIT_SESSION_REQUIRED_ERROR,
)


def test_standard_idx_ticker_without_stockbit_session_errors():
    error = FetchMarketProviderPrecondition().validate(
        FetchMarketProviderPreconditionRequest(
            tickers=["BBCA"],
            non_idx_tickers=frozenset(),
            candles_provider="yahoo",
            has_broker_session=False,
        )
    )
    assert error == STOCKBIT_SESSION_REQUIRED_ERROR


def test_non_idx_ticker_does_not_error():
    error = FetchMarketProviderPrecondition().validate(
        FetchMarketProviderPreconditionRequest(
            tickers=["^VIX"],
            non_idx_tickers=frozenset({"^VIX"}),
            candles_provider="yahoo",
            has_broker_session=False,
        )
    )
    assert error is None


def test_idx_provider_does_not_error():
    error = FetchMarketProviderPrecondition().validate(
        FetchMarketProviderPreconditionRequest(
            tickers=["BBCA"],
            non_idx_tickers=frozenset(),
            candles_provider="idx",
            has_broker_session=False,
        )
    )
    assert error is None


def test_stockbit_session_available_does_not_error():
    error = FetchMarketProviderPrecondition().validate(
        FetchMarketProviderPreconditionRequest(
            tickers=["BBCA"],
            non_idx_tickers=frozenset(),
            candles_provider="yahoo",
            has_broker_session=True,
        )
    )
    assert error is None


def test_first_failing_ticker_error_is_returned():
    error = FetchMarketProviderPrecondition().validate(
        FetchMarketProviderPreconditionRequest(
            tickers=["^VIX", "BBCA", "BMRI"],
            non_idx_tickers=frozenset({"^VIX"}),
            candles_provider="yahoo",
            has_broker_session=False,
        )
    )
    assert error == STOCKBIT_SESSION_REQUIRED_ERROR
