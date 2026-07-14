"""
Swing backtest execution/default config loaded from config/swing_backtest.yaml.

Layer: Infrastructure
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.infrastructure.config.app_config import AppConfig, load_app_config


def default_swing_backtest_config_path(config: AppConfig | None = None) -> Path:
    cfg = config or load_app_config()
    return Path(cfg.config_paths.swing_backtest)


@dataclass(frozen=True)
class SwingBacktestConfig:
    """Tunable defaults for walk-forward swing backtests."""

    capital: int = 100_000_000
    risk_pct: float = 1.0
    max_positions: int = 5
    take_profit_pct: float = 5.0
    stop_loss_pct: float = 5.0
    max_hold_days: int = 10
    cost_bps: float = 20.0
    entry_timing: str = "same_day_close"
    forward_data_lookahead_days: int = 45
    same_day_exit_priority: str = "stop_first"
    attribution_high_min_score: float = 70.0
    attribution_mid_min_score: float = 45.0


def load_swing_backtest_config(
    config_path: Path | None = None,
    config: AppConfig | None = None,
) -> SwingBacktestConfig:
    """Load swing backtest config. Defaults preserve existing behavior."""
    app_cfg = config or load_app_config()
    defaults = SwingBacktestConfig(
        capital=app_cfg.trading.capital,
        risk_pct=app_cfg.swing.risk_pct,
        take_profit_pct=app_cfg.swing.take_profit,
        stop_loss_pct=app_cfg.swing.stop_loss,
        max_hold_days=app_cfg.swing.max_hold,
        cost_bps=app_cfg.backtest.cost_bps,
    )
    raw = _read_yaml(config_path or default_swing_backtest_config_path(app_cfg))
    root = raw.get("swing_backtest") or raw
    if not isinstance(root, dict):
        return defaults

    portfolio = root.get("portfolio") or {}
    execution = root.get("execution") or {}
    attribution = root.get("attribution") or {}
    score_buckets = attribution.get("score_buckets") or {}
    return SwingBacktestConfig(
        capital=_int(portfolio, "capital", defaults.capital),
        risk_pct=_float(portfolio, "risk_pct", defaults.risk_pct),
        max_positions=_int(portfolio, "max_positions", defaults.max_positions),
        take_profit_pct=_float(execution, "take_profit_pct", defaults.take_profit_pct),
        stop_loss_pct=_float(execution, "stop_loss_pct", defaults.stop_loss_pct),
        max_hold_days=_int(execution, "max_hold_days", defaults.max_hold_days),
        cost_bps=_float(execution, "cost_bps", defaults.cost_bps),
        entry_timing=_str(execution, "entry_timing", defaults.entry_timing),
        forward_data_lookahead_days=_int(
            execution,
            "forward_data_lookahead_days",
            defaults.forward_data_lookahead_days,
        ),
        same_day_exit_priority=_str(
            execution,
            "same_day_exit_priority",
            defaults.same_day_exit_priority,
        ),
        attribution_high_min_score=_float(
            score_buckets,
            "high_min_score",
            defaults.attribution_high_min_score,
        ),
        attribution_mid_min_score=_float(
            score_buckets,
            "mid_min_score",
            defaults.attribution_mid_min_score,
        ),
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


def _str(data: dict[str, Any], key: str, default: str) -> str:
    return str(data[key]) if key in data else default
