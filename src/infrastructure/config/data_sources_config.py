"""
Data source preferences — loaded from config/data_sources.yaml.

Layer: Infrastructure
"""

from pathlib import Path

import yaml

_DATA_SOURCES_CONFIG_PATH = Path("config/data_sources.yaml")


def broker_summary_source() -> str:
    """Return broker_summary_source preference. Defaults to 'idx'."""
    try:
        with open(_DATA_SOURCES_CONFIG_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return str(data.get("broker_summary_source") or "idx").strip()
    except Exception:
        return "idx"


def idx_client_tuning() -> tuple[float, int, float]:
    """Return (request_delay_seconds, max_retries, retry_backoff_base) for IDX API clients."""
    defaults: tuple[float, int, float] = (1.0, 3, 2.0)
    try:
        with open(_DATA_SOURCES_CONFIG_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        idx = data.get("idx") or {}
        return (
            float(idx.get("request_delay_seconds", defaults[0])),
            int(idx.get("max_retries", defaults[1])),
            float(idx.get("retry_backoff_base", defaults[2])),
        )
    except Exception:
        return defaults


def candle_source() -> str:
    """Return candle_source preference. Falls back to APP_CFG.market.provider if absent."""
    try:
        with open(_DATA_SOURCES_CONFIG_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        value = data.get("candle_source")
        if value:
            return str(value).strip()
    except Exception:
        pass
    from src.infrastructure.config.app_config import APP_CFG
    return APP_CFG.market.provider
