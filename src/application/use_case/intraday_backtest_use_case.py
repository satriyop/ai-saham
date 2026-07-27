"""Daily-OHLC proxy simulation for the deterministic intraday pre-open workflow.

Uses daily OHLC as a proxy for intraday execution (Option A).

Layer: Application
Depends on: PreOpenPostOpenGatesUseCase, IndicatorRegistry, market+broker repositories
"""

from datetime import date

from src.application.dto.intraday_backtest import (
    PER_TRADE_CAPITAL_CAP_PCT,
    IntradayBacktestRequest,
    IntradayBacktestResponse,
    IntradayBacktestTrade,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.intraday_backtest_candidate_builder import (
    IntradayBacktestCandidateBuilder,
)
from src.application.services.intraday_backtest_report import (
    IntradayBacktestReportBuilder,
)
from src.application.services.intraday_backtest_simulator import (
    IntradayBacktestSimulator,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository

# Keep old imports working by re-exporting DTO classes
__all__ = [
    "IntradayBacktestRequest",
    "IntradayBacktestTrade",
    "IntradayBacktestResponse",
    "IntradayBacktestUseCase",
    "PER_TRADE_CAPITAL_CAP_PCT",
]


class IntradayBacktestUseCase:
    """Walk-forward intraday proxy simulation using daily OHLC.

    Delegates candidate building, daily simulation loops, and reporting to clean services.
    """

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        indicator_registry: IndicatorRegistry,
        iev_repository=None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = indicator_registry
        self._iev_repo = iev_repository

        # Inject components
        self._candidate_builder = IntradayBacktestCandidateBuilder(
            market_repository=market_repository,
            broker_repository=broker_repository,
            indicator_registry=indicator_registry,
        )
        self._simulator = IntradayBacktestSimulator(
            market_repository=market_repository,
            candidate_builder=self._candidate_builder,
            iev_repository=iev_repository,
        )
        self._report_builder = IntradayBacktestReportBuilder()

    def execute(self, request: IntradayBacktestRequest) -> IntradayBacktestResponse:
        self._validate(request)
        tickers = list(dict.fromkeys(t.upper().strip() for t in request.tickers))

        trading_dates = self._replay_dates(tickers, request.start_date, request.end_date)
        if not trading_dates:
            return self._report_builder.empty_response(
                request, ["No trading dates with candle data in range."]
            )

        # Run simulation
        result = self._simulator.run(
            tickers=tickers,
            trading_dates=trading_dates,
            request=request,
        )

        # Build response
        return self._report_builder.build_response(
            request=request,
            trades=result.trades,
            final_equity=result.final_equity,
            equity_curve=result.equity_curve,
            trading_days=result.trading_days,
            days_with_trades=result.days_with_trades,
            warnings=result.warnings,
        )

    def _replay_dates(self, tickers: list[str], start: date, end: date) -> list[date]:
        dates: set[date] = set()
        for ticker in tickers:
            candles = self._market_repo.get_candles(ticker, start_date=start, end_date=end)
            dates.update(c.date for c in candles)
        return sorted(dates)

    def _validate(self, request: IntradayBacktestRequest) -> None:
        if not request.tickers:
            raise ValueError("At least one ticker is required.")
        if request.start_date > request.end_date:
            raise ValueError("start_date must be <= end_date.")
        if request.capital <= 0:
            raise ValueError("capital must be positive.")
        if request.risk_pct <= 0:
            raise ValueError("risk_pct must be positive.")
        if request.max_daily_positions < 1:
            raise ValueError("max_daily_positions must be >= 1.")
        if request.max_stop_pct <= 0:
            raise ValueError("max_stop_pct must be positive.")
        if request.atr_range_cap_min > request.atr_range_cap_max:
            raise ValueError("atr_range_cap_min must be <= atr_range_cap_max.")
