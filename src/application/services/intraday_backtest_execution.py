"""Pure execution and position sizing calculations for intraday backtesting.

Layer: Application Service
"""

from decimal import Decimal

from src.application.dto.intraday_backtest import PER_TRADE_CAPITAL_CAP_PCT
from src.domain.value_objects.idx_market import SHARES_PER_LOT


def size_intraday_position(
    entry: Decimal,
    stop: Decimal,
    capital: Decimal,
    risk_pct: Decimal,
    cash: Decimal,
    cost_bps: Decimal,
) -> tuple[int, int]:
    """Compute (lots, shares) respecting risk, capital cap, and cash."""
    stop_distance = entry - stop
    if stop_distance <= 0:
        return 0, 0

    risk_amount = capital * risk_pct
    shares_by_risk = int(risk_amount / stop_distance)

    per_trade_cap = capital * PER_TRADE_CAPITAL_CAP_PCT
    shares_by_cap = int(per_trade_cap / entry) if entry > 0 else 0

    cost_multiplier = Decimal("1") + cost_bps / Decimal("10000")
    shares_by_cash = int(cash / (entry * cost_multiplier)) if cash > 0 and entry > 0 else 0

    shares = min(shares_by_risk, shares_by_cap, shares_by_cash)
    lots = shares // SHARES_PER_LOT
    return lots, lots * SHARES_PER_LOT


def compute_intraday_pnl(
    shares: int,
    entry: Decimal,
    exit_price: Decimal,
    cost_bps: Decimal,
) -> tuple[Decimal, float, float, Decimal]:
    """Return (pnl, gross_return_pct, net_return_pct, cost_total)."""
    entry_value = Decimal(shares) * entry
    exit_value = Decimal(shares) * exit_price
    entry_cost = entry_value * cost_bps / Decimal("10000")
    exit_cost = exit_value * cost_bps / Decimal("10000")
    cost_total = entry_cost + exit_cost
    pnl = exit_value - exit_cost - entry_value - entry_cost
    gross_pct = round(float((exit_price - entry) / entry * 100), 4) if entry > 0 else 0.0
    net_pct = round(float(pnl / entry_value * 100), 4) if entry_value > 0 else 0.0
    return pnl, gross_pct, net_pct, cost_total
