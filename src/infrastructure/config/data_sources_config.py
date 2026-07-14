"""
Data source preferences — loaded from AppConfig.

Layer: Infrastructure
"""

from src.infrastructure.config.app_config import load_app_config


def broker_summary_source() -> str:
    """Return broker_summary_source preference."""
    return load_app_config().broker.provider


def idx_client_tuning() -> tuple[float, int, float]:
    """Return (request_delay_seconds, max_retries, retry_backoff_base) for IDX API clients."""
    cfg = load_app_config()
    return (
        cfg.market.idx_request_delay_seconds,
        cfg.market.idx_max_retries,
        cfg.market.idx_retry_backoff_base,
    )


def candle_source() -> str:
    """Return candle_source preference."""
    return load_app_config().market.provider
