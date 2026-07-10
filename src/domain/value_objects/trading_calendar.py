"""
Pure calendar helpers for IDX trading-day fallback logic.

Layer: Domain

No I/O, no config, no repository access. `last_weekday` is a Mon-Fri
fallback only — it does NOT account for IDX public holidays. Callers that
need the true last trading session must combine this with a cached-data
lookup (see application/services/market_freshness_service.py).
"""

from datetime import date, timedelta


def last_weekday(as_of: date) -> date:
    """Most recent Mon-Fri on or before as_of."""
    if as_of.weekday() == 5:   # Saturday -> Friday
        return as_of - timedelta(days=1)
    if as_of.weekday() == 6:   # Sunday -> Friday
        return as_of - timedelta(days=2)
    return as_of
