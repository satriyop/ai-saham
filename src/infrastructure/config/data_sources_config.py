"""
Data source preferences — loaded from APP_CFG.

Layer: Infrastructure
"""

from src.infrastructure.config.app_config import APP_CFG


def broker_summary_source() -> str:
    """Return broker_summary_source preference."""
    return APP_CFG.broker.provider


def idx_client_tuning() -> tuple[float, int, float]:
    """Return (request_delay_seconds, max_retries, retry_backoff_base) for IDX API clients."""
    return (
        APP_CFG.market.idx_request_delay_seconds,
        APP_CFG.market.idx_max_retries,
        APP_CFG.market.idx_retry_backoff_base,
    )


def candle_source() -> str:
    """Return candle_source preference."""
    return APP_CFG.market.provider
