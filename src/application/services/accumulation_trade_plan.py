"""
AccumulationTradePlan service.

Computes trade setup targets from percent plans.

Layer: Application
"""

from __future__ import annotations

from decimal import Decimal


def compute_percent_plan(
    entry: Decimal,
    stop_pct: Decimal,
    target_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """Compute stop and target prices from a percentage plan."""
    stop = entry * (Decimal("1") - stop_pct / Decimal("100"))
    target = entry * (Decimal("1") + target_pct / Decimal("100"))
    return stop, target
