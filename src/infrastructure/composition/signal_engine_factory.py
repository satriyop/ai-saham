"""
Signal engine construction (infrastructure composition root).

Wires a fully-configured SignalEngine: loads signal-related config via the
shared application-layer config resolvers and injects Stockbit-backed
enrichment providers. This is concrete wiring, so it lives in
infrastructure, not application.

Layer: Infrastructure (composition root)
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.engine_bootstrap.signal_scoring_config_resolver import (
    resolve_signal_engine_config,
)
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.browser.stockbit_forward_estimates import (
    StockbitForwardEstimatesProvider,
)
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
    StockbitSQLiteConnectionProvider,
)
from src.infrastructure.config.signal_engine_config_loader import (
    load_signal_engine_config_raw,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def create_signal_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
    *,
    config: SignalEngineConfig | None = None,
) -> "SignalEngine":
    """
    Create a fully-configured SignalEngine.

    Args:
        db_path: Path to the SQLite database (e.g. data/db/data.db).
        with_enrichment: When True, inject all 5 Stockbit enrichment providers
            (bandar, fundamentals, seasonality, analyst, forward_estimates) using
            the SQLite cache so contextual evaluation has real enrichment data
            without a live broker session. When False (default), all providers
            are None and canonical evidence groups fed by them are MISSING —
            useful for testing the engine wiring.
        config: Optional pre-resolved ``SignalEngineConfig``. When provided, it
            is used by identity (no second YAML resolve). Required for corpus
            capture so snapshots and engines share the same typed policy object.
    """
    if config is not None:
        signal_config = config
    else:
        signal_config = resolve_signal_engine_config(load_signal_engine_config_raw())

    if not with_enrichment:
        return SignalEngine(config=signal_config)

    resolved = Path(db_path)
    market_repository = SQLiteMarketRepository(db_path=resolved)

    def _latest_close(ticker: str) -> float | None:
        candles = market_repository.get_candles(ticker)
        if not candles:
            return None
        return float(candles[-1].close)

    connection_provider = StockbitSQLiteConnectionProvider()
    stockbit_config = load_stockbit_provider_config()
    return SignalEngine(
        bandar_provider=StockbitBandarDetectorProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        insider_activity_provider=StockbitInsiderActivityProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        seasonality_provider=StockbitSeasonalityProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        analyst_provider=StockbitAnalystConsensusProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        forward_estimates_provider=StockbitForwardEstimatesProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        latest_price_provider=_latest_close,
        config=signal_config,
    )
