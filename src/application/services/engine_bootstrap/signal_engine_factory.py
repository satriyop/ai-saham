"""
Signal engine construction.

Wires a fully-configured SignalEngine: loads signal-related config via the
shared config resolvers and injects enrichment providers. No CLI policy, no
backtest/screening workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.application.services.engine_bootstrap.config_resolvers import (
    _load_engine_config,
)
from src.application.services.engine_bootstrap.signal_config_resolvers import (
    _resolve_signal_config,
    _resolve_signal_weights,
)

if TYPE_CHECKING:
    from src.application.services.signal_engine import SignalEngine


def create_signal_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
) -> "SignalEngine":
    """
    Create a fully-configured SignalEngine.

    Args:
        db_path: Path to the SQLite database (e.g. data/db/data.db).
        with_enrichment: When True, inject all 5 Stockbit enrichment providers
            (bandar, fundamentals, seasonality, analyst, forward_estimates) using
            the SQLite cache so evaluate() works without a live broker session.
            When False (default), all providers are None and all factors fall
            back to neutral (50.0) — useful for testing the engine wiring.
    """
    from pathlib import Path as _Path

    from src.application.services.signal_engine import SignalEngine
    from src.infrastructure.config.app_config import APP_CFG

    cfg = _load_engine_config(Path(APP_CFG.config_paths.signal_engine))
    weights = _resolve_signal_weights(cfg)
    signal_config = _resolve_signal_config(cfg)

    if not with_enrichment:
        return SignalEngine(weights=weights, config=signal_config)

    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.browser.stockbit_insider import (
        StockbitInsiderActivityProvider,
    )
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )

    resolved = _Path(db_path)
    market_repository = SQLiteMarketRepository(db_path=resolved)

    def _latest_close(ticker: str) -> float | None:
        candles = market_repository.get_candles(ticker)
        if not candles:
            return None
        return float(candles[-1].close)

    return SignalEngine(
        bandar_provider=StockbitBandarDetectorProvider(api_client=None, db_path=resolved),
        insider_activity_provider=StockbitInsiderActivityProvider(
            api_client=None, db_path=resolved
        ),
        seasonality_provider=StockbitSeasonalityProvider(api_client=None, db_path=resolved),
        analyst_provider=StockbitAnalystConsensusProvider(api_client=None, db_path=resolved),
        forward_estimates_provider=StockbitForwardEstimatesProvider(
            api_client=None, db_path=resolved
        ),
        latest_price_provider=_latest_close,
        weights=weights,
        config=signal_config,
    )
