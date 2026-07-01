"""Canonical benchmark ticker helpers.

Layer: Domain
"""

CANONICAL_BENCHMARK_TICKER = "IHSG"
YAHOO_BENCHMARK_TICKER = "^JKSE"

_BENCHMARK_ALIASES = {
    CANONICAL_BENCHMARK_TICKER,
    YAHOO_BENCHMARK_TICKER,
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
