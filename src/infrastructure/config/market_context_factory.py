"""
Market Context Engine construction helpers.

Layer: Infrastructure
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from datetime import date
from pathlib import Path

from src.application.services.market_context_engine import MarketContextEngine
from src.application.services.mce_observation_identity import build_mce_observation_identity
from src.application.services.universe_loader import resolve_tickers
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker
from src.domain.value_objects.market_context import MarketContext
from src.infrastructure.config.market_context_config import (
    default_market_context_config_path,
    load_market_context_config,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_context_repository import (
    SQLiteMarketContextRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_regime_observation_repository import (
    SQLiteRegimeObservationRepository,
)


def create_market_context_engine(
    *,
    db_path: Path,
    universe: str,
    benchmark: str = "IHSG",
) -> MarketContextEngine:
    """Construct MCE with local SQLite repositories and configured universe."""
    from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
    tickers = resolve_tickers(
        universe=universe,
        explicit=[],
        db_path=db_path,
        loader=YamlUniverseConfigLoader(),
        repository=SQLiteBrokerRepository(db_path),
    )
    config = load_market_context_config()
    benchmark = canonicalize_ticker(benchmark) if benchmark else benchmark
    if benchmark and benchmark != config.idx_trend.benchmark_ticker:
        config = dc_replace(
            config,
            idx_trend=dc_replace(config.idx_trend, benchmark_ticker=benchmark),
        )
    config_path = default_market_context_config_path()
    raw_yaml = config_path.read_text(encoding="utf-8")
    mce_identity = build_mce_observation_identity(
        resolved_mce_config_canonical=raw_yaml,
        universe_name=universe,
        benchmark_ticker=benchmark or "IHSG",
    )
    return MarketContextEngine(
        market_repository=SQLiteMarketRepository(db_path=db_path),
        config=config,
        universe=tickers,
        broker_repository=SQLiteBrokerRepository(db_path=db_path),
        context_repository=SQLiteMarketContextRepository(db_path=db_path),
        regime_observation_repository=SQLiteRegimeObservationRepository(db_path=db_path),
        mce_identity=mce_identity,
    )



def evaluate_market_context(
    *,
    db_path: Path,
    as_of_date: date,
    universe: str,
    benchmark: str = "IHSG",
) -> MarketContext:
    """Evaluate MCE through the standard local-first construction path."""
    engine = create_market_context_engine(
        db_path=db_path,
        universe=universe,
        benchmark=benchmark,
    )
    return engine.evaluate(as_of_date=as_of_date)
