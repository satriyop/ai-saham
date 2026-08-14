"""Composition root for StockbitAuthPort (production adapter).

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

from src.application.ports.stockbit_auth import StockbitAuthPort
from src.infrastructure.browser.stockbit_auth_adapter import StockbitAuthAdapter
from src.infrastructure.config.stockbit_config import StockbitConfig


def create_stockbit_auth_port(
    *,
    profile_dir: Path | None = None,
    stockbit_config: StockbitConfig | None = None,
    reauth_timeout: int = 180,
) -> StockbitAuthPort:
    """Build the production auth port. Tests may patch this factory."""
    return StockbitAuthAdapter(
        profile_dir,
        stockbit_config=stockbit_config,
        reauth_timeout=reauth_timeout,
    )
