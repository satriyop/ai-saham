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


def candle_source() -> str:
    """Return candle_source preference. Defaults to 'yahoo'."""
    try:
        with open(_DATA_SOURCES_CONFIG_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return str(data.get("candle_source") or "yahoo").strip()
    except Exception:
        return "yahoo"
