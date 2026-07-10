"""Backtest statistics helpers.

Layer: Application Service
"""

from decimal import Decimal
from typing import Iterable

from src.application.dto.swing_backtest import SwingBacktestDailyEquity, SwingBacktestTrade
from src.application.services.stats import (
    average,
    max_drawdown_pct,
    pct_change,
    profit_factor,
    win_rate,
)


def pct_change_pct(value: Decimal | float | int, base: Decimal | float | int) -> float:
    """Wrapper for pct_change with precision=4."""
    return pct_change(value, base, precision=4)


def average_pct(values: Iterable[float | None]) -> float | None:
    """Wrapper for average with precision=4."""
    return average(values, precision=4)


def win_rate_pct(values: Iterable[float | None]) -> float | None:
    """Wrapper for win_rate with precision=2."""
    return win_rate(values, precision=2)


def trade_profit_factor(trades: Iterable[SwingBacktestTrade]) -> float | None:
    """Wrapper for profit_factor with precision=4."""
    return profit_factor((trade.pnl for trade in trades), precision=4)


def equity_max_drawdown_pct(curve: Iterable[SwingBacktestDailyEquity]) -> float:
    """Wrapper for max_drawdown_pct with precision=4."""
    return max_drawdown_pct((point.equity for point in curve), precision=4)
