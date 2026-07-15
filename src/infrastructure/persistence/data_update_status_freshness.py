"""Freshness classification helpers for data update status read model.

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date, datetime


def range_label(min_raw: str | None, max_raw: str | None) -> str:
    if not min_raw or not max_raw:
        return "-"
    if min_raw == max_raw:
        return str(max_raw)[:10]
    return f"{str(min_raw)[:10]}..{str(max_raw)[:10]}"


def parse_dateish(raw: str | None, freshness: str) -> date | None:
    if not raw:
        return None
    value = str(raw)
    if freshness == "month":
        try:
            year, month = value.split("-", 1)
            return date(int(year), int(month), 1)
        except (ValueError, TypeError):
            return None
    for candidate in (value[:10], value):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    return None


def freshness_status(
    *,
    table: str,
    freshness: str,
    rows: int,
    ticker_count: int,
    requested_tickers: int,
    max_raw: str | None,
    expected_trading_day: date | None,
    today: date,
    market_is_open: bool = False,
) -> tuple[str, str, str | None]:
    if rows <= 0:
        return (
            "empty",
            "No rows for requested tickers.",
            f"{table} has no rows for requested tickers",
        )

    partial_issue = None
    if ticker_count < requested_tickers:
        partial_issue = (
            f"{table} has {ticker_count}/{requested_tickers} requested tickers"
        )

    max_date = parse_dateish(max_raw, freshness)

    if freshness == "range" and expected_trading_day is not None:
        if max_date is None or max_date < expected_trading_day:
            if (
                market_is_open
                and max_date is not None
                and (expected_trading_day - max_date).days <= 3
            ):
                return (
                    "pending-eod",
                    "EOD not yet available. Re-fetch after close.",
                    None,
                )
            return (
                "stale",
                f"Latest stored date is before expected trading day {expected_trading_day}.",
                partial_issue or f"{table} is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", "Current through today.", None

    if freshness == "today":
        if max_date != today:
            return (
                "stale",
                f"Latest fetched date is not today ({today}).",
                partial_issue or f"{table} cache is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", "Fetched today.", None

    if freshness == "month":
        current_month = f"{today.year:04d}-{today.month:02d}"
        if str(max_raw or "") != current_month:
            return (
                "stale",
                f"Latest fetched month is not current month ({current_month}).",
                partial_issue or f"{table} cache is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", "Fetched for current month.", None

    ttl_days = 30 if freshness == "ttl30" else 7 if freshness == "ttl7" else None
    if ttl_days is not None:
        if max_date is None or (today - max_date).days > ttl_days:
            return (
                "stale",
                f"Latest cache is older than {ttl_days}d TTL.",
                partial_issue or f"{table} cache is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", f"Fresh within {ttl_days}d TTL.", None

    if partial_issue:
        return "partial", "Some requested tickers are missing.", partial_issue
    return "ready", "Rows exist for requested tickers.", None
