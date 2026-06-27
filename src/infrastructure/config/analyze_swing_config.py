"""
Analyze swing workflow defaults loaded from config/analyze_swing.yaml.

Layer: Infrastructure
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.infrastructure.config.app_config import APP_CFG

ANALYZE_SWING_CONFIG_PATH = Path(APP_CFG.config_paths.analyze_swing)


@dataclass(frozen=True)
class AnalyzeSwingConfig:
    """Tunable workflow defaults for saham analyze swing."""

    market_refresh_days: int = 365
    broker_refresh_days: int = 90
    sentiment_max_headlines: int = 20
    sentiment_days: int = 3
    flow_detail_window_sessions: int = 30
    candidate_min_net_buy_days: int = 0
    candidate_min_score: float = 0.0


def load_analyze_swing_config(config_path: Path | None = None) -> AnalyzeSwingConfig:
    defaults = AnalyzeSwingConfig()
    raw = _read_yaml(config_path or ANALYZE_SWING_CONFIG_PATH)
    root = raw.get("analyze_swing") or raw
    if not isinstance(root, dict):
        return defaults
    refresh = root.get("auto_refresh") or {}
    sentiment = root.get("sentiment") or {}
    evidence = root.get("evidence") or {}
    candidate = root.get("candidate") or {}
    return AnalyzeSwingConfig(
        market_refresh_days=_int(refresh, "market_days", defaults.market_refresh_days),
        broker_refresh_days=_int(refresh, "broker_days", defaults.broker_refresh_days),
        sentiment_max_headlines=_int(
            sentiment,
            "max_headlines",
            defaults.sentiment_max_headlines,
        ),
        sentiment_days=_int(sentiment, "days", defaults.sentiment_days),
        flow_detail_window_sessions=_int(
            evidence,
            "flow_detail_window_sessions",
            defaults.flow_detail_window_sessions,
        ),
        candidate_min_net_buy_days=_int(
            candidate,
            "min_net_buy_days",
            defaults.candidate_min_net_buy_days,
        ),
        candidate_min_score=_float(candidate, "min_score", defaults.candidate_min_score),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def _int(data: dict[str, Any], key: str, default: int) -> int:
    return int(data[key]) if key in data else default


def _float(data: dict[str, Any], key: str, default: float) -> float:
    return float(data[key]) if key in data else default
