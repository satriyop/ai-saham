"""
Swing backtest execution/default config loaded from config/swing_backtest.yaml.

Layer: Infrastructure
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.infrastructure.config.app_config import APP_CFG

SWING_BACKTEST_CONFIG_PATH = Path(APP_CFG.config_paths.swing_backtest)


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


def load_swing_backtest_config(
    config_path: Path | None = None,
) -> SwingBacktestConfig:
    """Load swing backtest config. Defaults preserve existing behavior."""
    defaults = SwingBacktestConfig(
        capital=APP_CFG.trading.capital,
        risk_pct=APP_CFG.swing.risk_pct,
        take_profit_pct=APP_CFG.swing.take_profit,
        stop_loss_pct=APP_CFG.swing.stop_loss,
        max_hold_days=APP_CFG.swing.max_hold,
        cost_bps=APP_CFG.backtest.cost_bps,
    )
    raw = _read_yaml(config_path or SWING_BACKTEST_CONFIG_PATH)
    root = raw.get("swing_backtest") or raw
    if not isinstance(root, dict):
        return defaults

    portfolio = root.get("portfolio") or {}
    execution = root.get("execution") or {}
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
