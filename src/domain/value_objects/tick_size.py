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


def idx_tick_size(price: Decimal) -> Decimal:
    """Return the IDX tick size for a given price level.

    Args:
        price: Current price in IDR

    Returns:
        Tick size (1, 2, 5, 10, or 25 IDR)
    """
    return Decimal(str(for_price(price)))


def entry_price_from_bid(best_bid: Decimal, ticks_above: int = 1) -> Decimal:
    """Compute entry price as best_bid + N ticks (IDX-compliant tick sizing).

    Args:
        best_bid: Best bid price from order book
        ticks_above: Number of ticks above the best bid

    Returns:
        Entry price rounded to nearest valid tick
    """
    tick = idx_tick_size(best_bid)
    return best_bid + (tick * ticks_above)


def suggested_limit_from_close(
    prev_close: Decimal,
    suggested_limit_pct: Decimal = Decimal("0.005"),
) -> Decimal:
    """Compute a suggested limit order price from yesterday's close.

    Used as the entry_price in the call-auction-aware model:
    the trader places this limit AFTER the opening price is known,
    only if the open falls within the entry range.

    Args:
        prev_close: Yesterday's closing price
        suggested_limit_pct: Fraction above prev_close (default 0.5%)

    Returns:
        Suggested limit price rounded to the nearest valid IDX tick
    """
    raw = prev_close * (1 + suggested_limit_pct)
    tick = idx_tick_size(raw)
    # Round up to nearest tick
    ticks = int(raw / tick)
    rounded = tick * ticks
    if rounded < raw:
        rounded += tick
    return rounded
