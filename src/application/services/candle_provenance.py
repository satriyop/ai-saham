"""Helpers for local candle provenance used by application workflows.

Layer: Application
Depends on repository capabilities via duck typing only. No infrastructure
imports, providers, CLI, or AI.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def resolve_candle_source(
    market_repository: Any,
    *,
    ticker: str,
    as_of_date: date,
) -> str | None:
    """Return local candle source for ticker/as-of when repository exposes it."""
    getter = getattr(market_repository, "get_candle_source", None)
    if not callable(getter):
        return None
    return getter(ticker, as_of_date)
