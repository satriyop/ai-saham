"""
MarketContextEngine — first-class application service for market regime assessment.

Third pillar alongside RiskEngine and SignalEngine. Self-sufficient: callers call
evaluate() and get a MarketContext. No caller assembles factor data or reads config.

  evaluate(as_of_date, universe)    — fetches all data from injected repositories
  evaluate_with_data(request)       — pipeline path; caller provides pre-loaded data

Layer: Application
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from src.application.use_case.build_market_context_use_case import (
    BuildMarketContextRequest,
    BuildMarketContextUseCase,
)
from src.infrastructure.config.market_context_config import (
    MarketContextConfig,
    load_market_context_config,
)

if TYPE_CHECKING:
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_context_repository import MarketContextRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.market_context import MarketContext

logger = logging.getLogger(__name__)

# Lookback window for fetching historical candles (longest SMA period + buffer)
_CANDLE_LOOKBACK_DAYS = 180
# Broker flow only needs reference_days lookback (default 20); use a small buffer
_BROKER_LOOKBACK_DAYS = 30


class MarketContextEngine:
    """
    Self-sufficient market regime evaluation service.

    Fetches candles from the injected MarketDataRepository (SQLite cache).
    Optionally fetches foreign flow from BrokerDataRepository (aggregated across universe).
    Data must be pre-fetched via `saham fetch market` — this engine reads only.

    universe: list of ticker symbols used for idx_breadth + foreign_flow calculations.
    When universe is empty, both factors are unavailable.
    """

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        config: MarketContextConfig | None = None,
        universe: list[str] | None = None,
        broker_repository: "BrokerDataRepository | None" = None,
        context_repository: "MarketContextRepository | None" = None,
    ) -> None:
        self._repo = market_repository
        self._broker_repo = broker_repository
        self._context_repo = context_repository
        self._config = config or load_market_context_config()
        self._universe = [t.upper() for t in (universe or [])]
        self._use_case = BuildMarketContextUseCase()

    def evaluate(
        self,
        as_of_date: date | None = None,
    ) -> "MarketContext":
        """
        Full self-contained evaluation.

        Reads all factor data from the local SQLite cache.
        Returns MarketContext with staleness/coverage warnings if data is missing.
        """
        as_of = as_of_date or date.today()
        start = as_of - timedelta(days=_CANDLE_LOOKBACK_DAYS)

        cfg = self._config

        vix_candles      = self._fetch(cfg.vix.ticker, start, as_of)
        eido_candles     = self._fetch(cfg.eido.ticker, start, as_of)
        ihsg_candles     = self._fetch(cfg.idx_trend.benchmark_ticker, start, as_of)
        usd_idr_candles  = self._fetch(cfg.usd_idr.ticker, start, as_of)

        universe_candles: dict = {}
        if cfg.idx_breadth.enabled and self._universe:
            for ticker in self._universe:
                candles = self._fetch(ticker, start, as_of)
                if candles:
                    universe_candles[ticker] = candles

        foreign_flow_series = self._aggregate_foreign_flow(as_of) if cfg.foreign_flow.enabled else []

        request = BuildMarketContextRequest(
            config=cfg,
            as_of_date=as_of,
            vix_candles=vix_candles,
            eido_candles=eido_candles,
            ihsg_candles=ihsg_candles,
            usd_idr_candles=usd_idr_candles,
            universe_candles=universe_candles,
            foreign_flow_series=foreign_flow_series,
        )
        context = self._use_case.execute(request).context
        self._persist(context)
        return context

    def get_snapshot(self, as_of_date: date) -> "MarketContext | None":
        """Return a stored snapshot without re-evaluating. None if none persisted."""
        if self._context_repo is None:
            return None
        return self._context_repo.get(as_of_date)

    def get_recent_snapshots(self, limit: int = 30) -> "list[MarketContext]":
        """Return recent stored snapshots, newest first. Empty if no repo injected."""
        if self._context_repo is None:
            return []
        return self._context_repo.get_recent(limit)

    def _persist(self, context: "MarketContext") -> None:
        if self._context_repo is None:
            return
        try:
            self._context_repo.save(context)
        except Exception as exc:
            logger.debug("MarketContextEngine: failed to persist snapshot: %s", exc)

    def _aggregate_foreign_flow(self, as_of: date) -> list[tuple[date, Decimal]]:
        """
        Aggregate net foreign flow across all universe tickers by date.

        Returns list of (date, total_net_foreign_value) tuples, sorted ascending.
        Empty list if no broker repository or no universe.
        """
        if not self._broker_repo or not self._universe:
            return []

        start = as_of - timedelta(days=_BROKER_LOOKBACK_DAYS)
        daily_totals: dict[date, Decimal] = defaultdict(Decimal)

        for ticker in self._universe:
            try:
                summaries = self._broker_repo.get_broker_summaries(
                    ticker, start_date=start, end_date=as_of
                )
                for s in summaries:
                    daily_totals[s.date] += s.foreign_net_value
            except Exception as exc:
                logger.debug("MarketContextEngine: broker fetch failed for %s: %s", ticker, exc)

        return sorted(daily_totals.items(), key=lambda x: x[0])

    def evaluate_with_data(self, request: BuildMarketContextRequest) -> "MarketContext":
        """Pipeline path: caller provides pre-loaded data (avoids N+1 fetches in loops)."""
        return self._use_case.execute(request).context

    # ── internals ─────────────────────────────────────────────────────────────

    def _fetch(self, ticker: str, start: date, end: date) -> list:
        try:
            return self._repo.get_candles(ticker, start_date=start, end_date=end)
        except Exception as exc:
            logger.debug("MarketContextEngine: fetch failed for %s: %s", ticker, exc)
            return []
