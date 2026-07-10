"""Tests for RefreshMarketContextInputsUseCase — pure application logic.

No infrastructure is monkeypatched here: the use case takes pre-resolved
ticker inputs and an injected `refresh_ticker` callable, so tests exercise
it exactly as the adapter wiring layer does.
"""

from src.application.use_case.refresh_market_context_inputs_use_case import (
    GlobalContextTickerInput,
    RefreshMarketContextInputsRequest,
    RefreshMarketContextInputsUseCase,
)


def test_passes_each_ticker_days_and_tolerance_to_refresh_ticker():
    captured: list[tuple[str, int, int]] = []

    def fake_refresh_ticker(ticker: str, days: int, end_tolerance_days: int) -> str:
        captured.append((ticker, days, end_tolerance_days))
        return "+1rows/span=1d"

    request = RefreshMarketContextInputsRequest(
        tickers=(
            GlobalContextTickerInput(ticker="^VIX", factor="vix", end_tolerance_days=5),
            GlobalContextTickerInput(ticker="EIDO", factor="eido", end_tolerance_days=5),
        ),
        days=180,
        refresh_ticker=fake_refresh_ticker,
    )

    response = RefreshMarketContextInputsUseCase().execute(request)

    assert captured == [
        ("^VIX", 180, 5),
        ("EIDO", 180, 5),
    ]
    assert response.statuses == (
        "^VIX(vix):+1rows/span=1d",
        "EIDO(eido):+1rows/span=1d",
    )


def test_normalizes_cached_prefixed_status_to_checkmark():
    def fake_refresh_ticker(ticker: str, days: int, end_tolerance_days: int) -> str:
        return "cached-current"

    request = RefreshMarketContextInputsRequest(
        tickers=(GlobalContextTickerInput(ticker="IDR=X", factor="usd_idr", end_tolerance_days=1),),
        days=180,
        refresh_ticker=fake_refresh_ticker,
    )

    response = RefreshMarketContextInputsUseCase().execute(request)

    assert response.statuses == ("IDR=X(usd_idr):✓",)


def test_isolates_per_ticker_exceptions():
    def flaky_refresh_ticker(ticker: str, days: int, end_tolerance_days: int) -> str:
        if ticker == "^VIX":
            raise RuntimeError("network unreachable")
        return "+2rows/span=2d"

    request = RefreshMarketContextInputsRequest(
        tickers=(
            GlobalContextTickerInput(ticker="^VIX", factor="vix", end_tolerance_days=1),
            GlobalContextTickerInput(ticker="EIDO", factor="eido", end_tolerance_days=1),
        ),
        days=180,
        refresh_ticker=flaky_refresh_ticker,
    )

    response = RefreshMarketContextInputsUseCase().execute(request)

    assert response.statuses[0].startswith("^VIX(vix):ERR:")
    assert response.statuses[1] == "EIDO(eido):+2rows/span=2d"


def test_empty_ticker_tuple_returns_empty_statuses():
    request = RefreshMarketContextInputsRequest(
        tickers=(),
        days=180,
        refresh_ticker=lambda ticker, days, end_tolerance_days: "unused",
    )

    response = RefreshMarketContextInputsUseCase().execute(request)

    assert response.statuses == ()
