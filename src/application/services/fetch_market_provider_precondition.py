"""
Command precondition for `saham fetch market`: fail fast before the
per-ticker loop if any ticker in the batch would fail candle-provider
resolution (regular IDX ticker, provider != idx, no Stockbit session).

This is a command precondition, not a per-ticker transient fetch failure:
every affected ticker would fail identically, so the command must fail fast
before starting the ticker loop instead of surfacing a raw exception
mid-run.

Layer: Application
"""

from dataclasses import dataclass

from src.application.use_case.resolve_candle_provider_policy_use_case import (
    ResolveCandleProviderPolicyRequest,
    ResolveCandleProviderPolicyUseCase,
)


@dataclass(frozen=True)
class FetchMarketProviderPreconditionRequest:
    tickers: list[str]
    non_idx_tickers: frozenset[str]
    candles_provider: str
    has_broker_session: bool


class FetchMarketProviderPrecondition:
    """Validates candle-provider fetchability for a batch of tickers."""

    def validate(
        self,
        request: FetchMarketProviderPreconditionRequest,
    ) -> str | None:
        """
        Return the candle-provider policy error message for the first
        ticker that would fail provider resolution, or None if the batch
        is fetchable as-is.
        """
        policy_use_case = ResolveCandleProviderPolicyUseCase()
        for ticker in request.tickers:
            decision = policy_use_case.execute(
                ResolveCandleProviderPolicyRequest(
                    ticker=ticker,
                    non_idx_tickers=request.non_idx_tickers,
                    requested_provider_name=request.candles_provider,
                    has_broker_session=request.has_broker_session,
                )
            )
            if decision.error is not None:
                return decision.error
        return None
