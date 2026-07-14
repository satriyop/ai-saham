"""
Stockbit config composition helper.

Single entry point for loading `StockbitConfig` at a composition boundary.
Callers load once here and pass the returned instance explicitly into every
Stockbit provider/client they construct, instead of letting each provider
fall back to its own `load_stockbit_config()` call.

Layer: Infrastructure
"""

from __future__ import annotations

from src.infrastructure.config.stockbit_config import StockbitConfig, load_stockbit_config


def load_stockbit_provider_config() -> StockbitConfig:
    """Load the `StockbitConfig` shared by a Stockbit provider composition call."""
    return load_stockbit_config()
