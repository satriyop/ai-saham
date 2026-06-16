"""
IDX tick size (fraksi harga) per BEI regulation Kep-00196/BEI/12-2024.

Graduated table mapping price tiers to minimum price movement (tick):
  < Rp 200        → Rp 1
  Rp 200–499      → Rp 2
  Rp 500–1,999    → Rp 5
  Rp 2,000–4,999  → Rp 10
  ≥ Rp 5,000      → Rp 25

Layer: Domain (pure function — no I/O, no external dependencies)
"""

from decimal import Decimal


def for_price(price: Decimal) -> int:
    """Return the IDX tick size (in IDR) for a given stock price.

    Args:
        price: Stock price in IDR (must be > 0)

    Returns:
        Minimum price movement in IDR per the current BEI regulation.
    """
    if price <= 0:
        raise ValueError(f"Price must be positive, got {price}")
    if price < Decimal("200"):
        return 1
    if price < Decimal("500"):
        return 2
    if price < Decimal("2000"):
        return 5
    if price < Decimal("5000"):
        return 10
    return 25


def ticks_between(lower: Decimal, upper: Decimal) -> int:
    """Return the number of ticks separating two prices at the lower price's tier.

    Uses the tick size of the lower price as the reference tier.
    Returns 0 if upper <= lower.
    """
    if upper <= lower:
        return 0
    tick = for_price(lower)
    return int((upper - lower) / tick)
