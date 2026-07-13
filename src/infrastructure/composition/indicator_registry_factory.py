"""
Indicator registry construction (infrastructure composition root).

Builds an IndicatorRegistry with built-in indicators, discovered plugins, and
persisted formulas loaded. This is concrete wiring — it constructs the
infrastructure plugin loader and formula storage directly — so it lives in
infrastructure, not application. Adapters call this to obtain a fully-wired
registry and pass it explicitly into application use cases.

Layer: Infrastructure (composition root)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.formula.parser import parse
from src.application.services.indicator_registry import IndicatorRegistry
from src.infrastructure.persistence.formula_storage import FormulaStorage
from src.infrastructure.plugins.indicator_loader import IndicatorPluginLoader

if TYPE_CHECKING:
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository

logger = logging.getLogger(__name__)


def create_indicator_registry(
    plugin_dir: str | None = None,
    formula_storage: "FormulaStorage | None" = None,
    load_formulas: bool = True,
    broker_repository: "BrokerDataRepository | None" = None,
    market_repository: "MarketDataRepository | None" = None,
    index_ticker: str = "IHSG",
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

    loader = IndicatorPluginLoader(Path(plugin_dir) if plugin_dir else None)
    plugins = loader.discover()

    for plugin_class in plugins:
        try:
            registry.register_plugin(plugin_class)
            logger.debug(f"Registered plugin: {plugin_class.name}")
        except Exception as e:
            logger.warning(f"Failed to register plugin {plugin_class.name}: {e}")

    if load_formulas:
        _load_formulas_into_registry(registry, formula_storage)

    return registry


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
    if formula_storage is None:
        formula_storage = FormulaStorage()

    try:
        stored_formulas = formula_storage.load_all()
    except Exception as e:
        logger.warning(f"Failed to load formulas from storage: {e}")
        return

    if not stored_formulas:
        logger.debug("No formulas found in storage")
        return

    loaded_count = 0
    for name, stored in stored_formulas.items():
        try:
            ast = parse(stored.formula)
            registry.register_formula(name, ast)
            logger.debug(f"Loaded formula from storage: {name}")
            loaded_count += 1
        except Exception as e:
            logger.warning(f"Failed to load formula {name}: {e}")

    if loaded_count > 0:
        logger.info(f"Loaded {loaded_count} formulas from storage")
