"""
Small adapter factory for constructing a cached-only broker distribution provider.

Layer: Adapter (wiring only, no fetch/network behavior)
"""

from __future__ import annotations

from pathlib import Path

from src.domain.ports.broker_distribution_provider import BrokerDistributionProvider


def create_broker_distribution_provider(db_path: Path) -> BrokerDistributionProvider:
    from src.infrastructure.browser.stockbit_broker_distribution import (
        StockbitBrokerDistributionProvider,
    )

    return StockbitBrokerDistributionProvider(api_client=None, db_path=db_path)
