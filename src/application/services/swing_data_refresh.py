"""
Swing analysis refresh orchestration.

Layer: Application
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def refresh_swing_data(
    *,
    ticker: str,
    db_path: Path,
    force_refresh: bool,
    market_refresh_days: int,
    broker_refresh_days: int,
    fetch_candles: Callable[..., str],
    create_broker_provider: Callable[..., tuple[object, str]],
    fetch_broker: Callable[..., object],
) -> tuple[str, ...]:
    """Refresh only the requested ticker for swing analysis."""
    actions: list[str] = []
    broker_provider, broker_provider_name = create_broker_provider(None)
    candles_status = fetch_candles(
        ticker=ticker,
        days=market_refresh_days,
        db_path=db_path,
        provider_name="stockbit",
        refresh=force_refresh,
        broker_provider=broker_provider,
    )
    actions.append(f"candles={candles_status}")
    broker_status = fetch_broker(
        ticker=ticker,
        days=broker_refresh_days,
        db_path=db_path,
        broker_provider=broker_provider,
        refresh=force_refresh,
    )
    actions.append(f"broker({broker_provider_name})={broker_status}")

    return tuple(actions)
