"""Infrastructure config-backed market context provider.

Layer: Application Service / Infrastructure Adapter
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from src.application.services.market_context_engine import MarketContextEngine
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker
from src.domain.value_objects.market_context import MarketContext
from src.infrastructure.config.market_context_config import load_market_context_config


class ConfigBackedMarketContextProvider:
    """Evaluates market regimes using market context engine and infrastructure configurations."""

    def __init__(
        self,
        *,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository

    def evaluate_for_dates(
        self,
        *,
        tickers: list[str],
        replay_dates: list[date],
        benchmark_ticker: str,
    ) -> dict[date, MarketContext]:
        """Evaluate market context for given dates using local configuration."""
        cfg = load_market_context_config()
        benchmark = canonicalize_ticker(benchmark_ticker)

        if benchmark != cfg.idx_trend.benchmark_ticker:
            cfg = replace(
                cfg,
                idx_trend=replace(cfg.idx_trend, benchmark_ticker=benchmark),
            )

        engine = MarketContextEngine(
            market_repository=self._market_repo,
            config=cfg,
            universe=tickers,
            broker_repository=self._broker_repo,
        )

        return {
            replay_date: engine.evaluate(as_of_date=replay_date)
            for replay_date in replay_dates
        }
