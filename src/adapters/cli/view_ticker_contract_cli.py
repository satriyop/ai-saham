"""
CLI helpers for stock-axis view ticker contract (format + empty errors).

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.cli_errors import raise_data_unavailable
from src.application.dto.view_ticker_contract import (
    default_ticker_fetch_hint,
    missing_ticker_message,
)


def exit_missing_ticker_data(
    *,
    ticker: str,
    what: str,
    source: str | None = None,
    fetch_hint: str | None = None,
    for_date=None,
) -> None:
    """Print standardized missing-data message and exit as data_unavailable."""
    hint = fetch_hint or default_ticker_fetch_hint(ticker)
    message = missing_ticker_message(
        ticker=ticker,
        what=what,
        source=source,
        fetch_hint=hint,
        for_date=for_date,
    )
    # First line is the operator summary; full multi-line body stays in message.
    raise_data_unavailable(message)
