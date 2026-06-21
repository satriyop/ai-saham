"""
Position sizing service — pure computation, zero I/O.

Computes stop price, target price, lot count, and risk/reward amounts
from entry price + ATR + capital + risk %. All arithmetic uses Decimal
to stay consistent with the rest of the domain.

Layer: Application (service, not use case — no ports, no orchestration)
"""

from dataclasses import dataclass
from decimal import Decimal

from src.domain.value_objects.idx_market import SHARES_PER_LOT


@dataclass(frozen=True)
class SizingResult:
    entry_price: Decimal
    atr: Decimal
    atr_multiplier: Decimal
    stop_price: Decimal
    stop_distance: Decimal
    stop_pct: Decimal           # negative %
    target_price: Decimal
    target_pct: Decimal         # positive %
    reward_risk_ratio: Decimal
    capital: Decimal
    risk_amount: Decimal        # capital × risk_pct
    reward_amount: Decimal
    lots: int                   # floor(shares_raw / 100)
    shares: int                 # lots × 100
    position_cost: Decimal      # shares × entry_price
    capital_used_pct: Decimal


@dataclass(frozen=True)
class PercentSizingResult:
    entry_price: Decimal
    stop_pct_input: Decimal
    target_pct_input: Decimal
    stop_price: Decimal
    stop_distance: Decimal
    stop_pct: Decimal
    target_price: Decimal
    target_pct: Decimal
    capital: Decimal
    risk_amount: Decimal
    lots: int
    shares: int
    position_cost: Decimal
    capital_used_pct: Decimal


def compute_position_size(
    *,
    entry: Decimal,
    atr: Decimal,
    capital: Decimal,
    risk_pct: Decimal,
    atr_multiplier: Decimal = Decimal("1.5"),
    reward_risk: Decimal = Decimal("2.0"),
) -> SizingResult:
    """
    Compute position sizing from ATR-based stop and fixed fractional risk.

    Args:
        entry: Entry price in IDR
        atr: ATR(14) value in IDR
        capital: Total capital in IDR
        risk_pct: Fraction of capital at risk, e.g. Decimal("0.01") = 1%
        atr_multiplier: Stop = entry - multiplier × ATR
        reward_risk: Target = entry + reward_risk × stop_distance

    Returns:
        SizingResult with all computed values

    Raises:
        ValueError: If ATR is zero or negative
    """
    if atr <= Decimal("0"):
        raise ValueError(f"ATR must be positive, got {atr}")

    stop_distance = atr * atr_multiplier
    stop_price = entry - stop_distance
    stop_pct = (stop_price - entry) / entry * Decimal("100")

    target_distance = stop_distance * reward_risk
    target_price = entry + target_distance
    target_pct = (target_price - entry) / entry * Decimal("100")

    risk_amount = capital * risk_pct
    reward_amount = risk_amount * reward_risk

    # How many shares to buy: risk_amount / risk_per_share
    shares_raw = int(risk_amount / stop_distance)
    lots = shares_raw // SHARES_PER_LOT
    shares = lots * SHARES_PER_LOT

    position_cost = Decimal(str(shares)) * entry
    capital_used_pct = (
        position_cost / capital * Decimal("100") if capital > 0 else Decimal("0")
    )

    return SizingResult(
        entry_price=entry,
        atr=atr,
        atr_multiplier=atr_multiplier,
        stop_price=stop_price,
        stop_distance=stop_distance,
        stop_pct=stop_pct,
        target_price=target_price,
        target_pct=target_pct,
        reward_risk_ratio=reward_risk,
        capital=capital,
        risk_amount=risk_amount,
        reward_amount=reward_amount,
        lots=lots,
        shares=shares,
        position_cost=position_cost,
        capital_used_pct=capital_used_pct,
    )


def compute_percent_position_size(
    *,
    entry: Decimal,
    capital: Decimal,
    risk_pct: Decimal,
    stop_loss_pct: Decimal,
    take_profit_pct: Decimal,
) -> PercentSizingResult:
    """
    Compute position sizing from fixed percentage stop/target.

    Args:
        entry: Entry price in IDR
        capital: Total capital in IDR
        risk_pct: Fraction of capital at risk, e.g. Decimal("0.01") = 1%
        stop_loss_pct: Stop distance percent, e.g. Decimal("5") = 5%
        take_profit_pct: Target distance percent, e.g. Decimal("5") = 5%

    Returns:
        PercentSizingResult with lot-rounded position.

    Raises:
        ValueError: If entry, capital, risk, stop, or target is invalid
    """
    if entry <= Decimal("0"):
        raise ValueError("Entry price must be positive")
    if capital <= Decimal("0"):
        raise ValueError("Capital must be positive")
    if risk_pct <= Decimal("0"):
        raise ValueError("Risk percent must be positive")
    if stop_loss_pct <= Decimal("0"):
        raise ValueError("Stop loss percent must be positive")
    if take_profit_pct <= Decimal("0"):
        raise ValueError("Take profit percent must be positive")

    stop_distance = entry * stop_loss_pct / Decimal("100")
    stop_price = entry - stop_distance
    target_price = entry * (Decimal("1") + take_profit_pct / Decimal("100"))

    risk_amount = capital * risk_pct
    shares_raw = int(risk_amount / stop_distance)
    lots = shares_raw // SHARES_PER_LOT
    shares = lots * SHARES_PER_LOT
    position_cost = Decimal(str(shares)) * entry
    capital_used_pct = (
        position_cost / capital * Decimal("100") if capital > 0 else Decimal("0")
    )

    return PercentSizingResult(
        entry_price=entry,
        stop_pct_input=stop_loss_pct,
        target_pct_input=take_profit_pct,
        stop_price=stop_price,
        stop_distance=stop_distance,
        stop_pct=-stop_loss_pct,
        target_price=target_price,
        target_pct=take_profit_pct,
        capital=capital,
        risk_amount=risk_amount,
        lots=lots,
        shares=shares,
        position_cost=position_cost,
        capital_used_pct=capital_used_pct,
    )
