"""
Application bootstrap utilities.

Provides functions for initializing application services with plugins
and persisted formulas.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.formula.parser import parse
from src.application.services.indicator_registry import IndicatorRegistry

if TYPE_CHECKING:
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.infrastructure.persistence.formula_storage import FormulaStorage
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.signal_engine import SignalEngine

logger = logging.getLogger(__name__)


def create_indicator_registry(
    plugin_dir: str | None = None,
    formula_storage: "FormulaStorage | None" = None,
    load_formulas: bool = True,
    broker_repository: "BrokerDataRepository | None" = None,
    market_repository: "MarketDataRepository | None" = None,
    index_ticker: str = "^JKSE",
) -> IndicatorRegistry:
    """
    Create an IndicatorRegistry with plugins and formulas loaded.

    Discovers plugins from the specified directory (or default plugins/indicators/)
    and registers them. Optionally loads persisted formulas from storage.
    Gracefully handles missing directories, invalid plugins, and invalid formulas.

    Args:
        plugin_dir: Optional path to plugin directory. None uses default.
        formula_storage: Optional FormulaStorage instance for loading formulas.
                        If None and load_formulas is True, creates default storage.
        load_formulas: Whether to load formulas from storage. Default True.

    Returns:
        IndicatorRegistry with built-in indicators, discovered plugins,
        and loaded formulas.
    """
    registry = IndicatorRegistry(
        broker_repository=broker_repository,
        market_repository=market_repository,
        index_ticker=index_ticker,
    )

    # Load plugins
    from src.infrastructure.plugins.indicator_loader import IndicatorPluginLoader

    loader = IndicatorPluginLoader(Path(plugin_dir) if plugin_dir else None)
    plugins = loader.discover()

    # Register each plugin
    for plugin_class in plugins:
        try:
            registry.register_plugin(plugin_class)
            logger.debug(f"Registered plugin: {plugin_class.name}")
        except Exception as e:
            logger.warning(f"Failed to register plugin {plugin_class.name}: {e}")

    # Load persisted formulas
    if load_formulas:
        _load_formulas_into_registry(registry, formula_storage)

    return registry


def create_risk_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
) -> "RiskEngine":
    """
    Create a fully-configured RiskEngine with all three gates wired.

    Args:
        db_path: Path to the SQLite database (e.g. data/db/data.db).
        with_enrichment: When True, inject FundamentalsProvider and
            BandarDetectorProvider so FundamentalGate and BandarGate
            can fire from the engine's own assess() call.
            When False (default), LiquidityGate still fires from candle
            data; the other gates skip gracefully.
    """
    from pathlib import Path as _Path

    from src.application.services.risk_engine import RiskEngine
    from src.domain.rules.bandar_gate import BandarGate
    from src.domain.rules.free_float_gate import FreeFloatGate
    from src.domain.rules.fundamental_gate import FundamentalGate
    from src.domain.rules.liquidity_gate import LiquidityGate
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )

    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )

    resolved = _Path(db_path)
    repository = SQLiteMarketRepository(db_path=resolved)
    broker_repository = SQLiteBrokerRepository(db_path=resolved)
    registry = create_indicator_registry(
        market_repository=repository,
        broker_repository=broker_repository,
    )

    fund_prov = None
    bandar_prov = None
    shareholding_prov = None
    if with_enrichment:
        from src.infrastructure.browser.stockbit_fundamentals import (
            StockbitFundamentalsProvider,
        )
        from src.infrastructure.browser.stockbit_bandar import (
            StockbitBandarDetectorProvider,
        )
        from src.infrastructure.browser.stockbit_shareholding import (
            StockbitShareholdingProvider,
        )

        fund_prov = StockbitFundamentalsProvider(broker_provider=None, db_path=resolved)
        bandar_prov = StockbitBandarDetectorProvider(broker_provider=None, db_path=resolved)
        shareholding_prov = StockbitShareholdingProvider(broker_provider=None, db_path=resolved)

    return RiskEngine(
        repository=repository,
        registry=registry,
        structural_gates=[FundamentalGate(), LiquidityGate(), FreeFloatGate()],
        execution_gates=[BandarGate()],
        fundamentals_provider=fund_prov,
        bandar_provider=bandar_prov,
        shareholding_provider=shareholding_prov,
    )


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

    if not with_enrichment:
        return SignalEngine()

    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )

    resolved = _Path(db_path)
    return SignalEngine(
        bandar_provider=StockbitBandarDetectorProvider(broker_provider=None, db_path=resolved),
        fundamentals_provider=StockbitFundamentalsProvider(broker_provider=None, db_path=resolved),
        seasonality_provider=StockbitSeasonalityProvider(broker_provider=None, db_path=resolved),
        analyst_provider=StockbitAnalystConsensusProvider(broker_provider=None, db_path=resolved),
        forward_estimates_provider=StockbitForwardEstimatesProvider(
            broker_provider=None, db_path=resolved
        ),
    )


def _load_formulas_into_registry(
    registry: IndicatorRegistry,
    formula_storage: "FormulaStorage | None" = None,
) -> None:
    """
    Load persisted formulas into the registry.

    Args:
        registry: IndicatorRegistry to load formulas into.
        formula_storage: Optional FormulaStorage instance. If None,
                        creates default storage from config/formulas.yaml.
    """
    # Create default storage if not provided
    if formula_storage is None:
        from src.infrastructure.persistence.formula_storage import FormulaStorage

        formula_storage = FormulaStorage()

    # Load all formulas
    try:
        stored_formulas = formula_storage.load_all()
    except Exception as e:
        logger.warning(f"Failed to load formulas from storage: {e}")
        return

    if not stored_formulas:
        logger.debug("No formulas found in storage")
        return

    # Register each formula
    loaded_count = 0
    for name, stored in stored_formulas.items():
        try:
            # Parse formula string to AST
            ast = parse(stored.formula)

            # Register in registry
            registry.register_formula(name, ast)
            logger.debug(f"Loaded formula from storage: {name}")
            loaded_count += 1

        except Exception as e:
            logger.warning(f"Failed to load formula {name}: {e}")

    if loaded_count > 0:
        logger.info(f"Loaded {loaded_count} formulas from storage")
