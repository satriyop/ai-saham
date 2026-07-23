"""
Candle provider selection policy for `saham fetch market`.

Decides which candle data source a ticker must be fetched from — Yahoo for
global-context (non-IDX) tickers, Stockbit historical for the benchmark/IDX
tickers when a broker session is available, IDX market data when the CLI
explicitly requests `--provider idx`, and otherwise requires a Stockbit
session for correct IDX exchange volumes. Pure decision logic: no I/O, no
infrastructure imports. The adapter constructs the concrete provider class
named by the returned CandleProviderKind.

Layer: Application
"""

from dataclasses import dataclass
from enum import Enum

from src.domain.value_objects.benchmark_symbol import is_benchmark_ticker
from src.domain.value_objects.ticker_classifier import is_non_idx_ticker

STOCKBIT_SESSION_REQUIRED_ERROR = (
    "Stockbit session is required to fetch IDX tickers to ensure correct exchange volumes. "
    "Please run 'saham fetch stockbit login' first."
)


class CandleProviderKind(Enum):
    YAHOO = "yahoo"
    STOCKBIT_HISTORICAL = "stockbit_historical"
    IDX_MARKET = "idx_market"


@dataclass(frozen=True)
class ResolveCandleProviderPolicyRequest:
    ticker: str
    non_idx_tickers: frozenset[str]
    requested_provider_name: str
    has_broker_session: bool


@dataclass(frozen=True)
class ResolveCandleProviderPolicyResponse:
    provider_kind: CandleProviderKind | None
    error: str | None = None


class ResolveCandleProviderPolicyUseCase:
    """Pure candle-provider selection decision."""

    def execute(
        self, request: ResolveCandleProviderPolicyRequest
    ) -> ResolveCandleProviderPolicyResponse:
        if is_non_idx_ticker(request.ticker, request.non_idx_tickers):
            return ResolveCandleProviderPolicyResponse(CandleProviderKind.YAHOO)

        if is_benchmark_ticker(request.ticker):
            if request.has_broker_session:
                return ResolveCandleProviderPolicyResponse(CandleProviderKind.STOCKBIT_HISTORICAL)
            return ResolveCandleProviderPolicyResponse(CandleProviderKind.YAHOO)

        if request.requested_provider_name == "idx":
            return ResolveCandleProviderPolicyResponse(CandleProviderKind.IDX_MARKET)

        # Standard IDX stock ticker: Yahoo does not reliably report correct
        # IDX exchange volumes, so a Stockbit session is mandatory here.
        if not request.has_broker_session:
            return ResolveCandleProviderPolicyResponse(
                provider_kind=None, error=STOCKBIT_SESSION_REQUIRED_ERROR
            )
        return ResolveCandleProviderPolicyResponse(CandleProviderKind.STOCKBIT_HISTORICAL)
