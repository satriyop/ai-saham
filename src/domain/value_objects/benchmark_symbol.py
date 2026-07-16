"""Canonical benchmark ticker helpers.

Layer: Domain
"""

from dataclasses import dataclass

CANONICAL_BENCHMARK_TICKER = "IHSG"
YAHOO_IHSG_TICKER = "^JKSE"


@dataclass(frozen=True)
class BenchmarkTickerAliases:
    """Canonical benchmark ticker plus a legacy alias to check as fallback."""

    canonical: str
    legacy: str | None = None

_BENCHMARK_ALIASES = {
    CANONICAL_BENCHMARK_TICKER,
    YAHOO_IHSG_TICKER,
}


def is_benchmark_ticker(ticker: str) -> bool:
    """Return True when ticker is a known benchmark alias."""
    return ticker.upper().strip() in _BENCHMARK_ALIASES


def canonicalize_ticker(ticker: str) -> str:
    """Normalize known provider aliases to the canonical application ticker."""
    normalized = ticker.upper().strip()
    if normalized in _BENCHMARK_ALIASES:
        return CANONICAL_BENCHMARK_TICKER
    return normalized
