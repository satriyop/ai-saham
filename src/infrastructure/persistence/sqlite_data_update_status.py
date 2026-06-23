"""
SQLite read model for `saham fetch market` post-run database status.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.application.use_case.data_update_status_use_case import DataUpdateTableStatus


@dataclass(frozen=True)
class _TableSpec:
    table: str
    source: str
    contains: str
    date_column: str | None
    source_column: str | None = None
    source_value: str | None = None
    freshness: str = "range"
    applicable: bool = True
    skipped_reason: str | None = None


def build_data_update_table_statuses(
    db_path: Path,
    tickers: list[str],
    *,
    candles_provider: str,
    broker_provider_name: str,
    no_meta: bool,
    candles_only: bool,
    broker_only: bool,
    enrichment_available: bool,
    expected_trading_day: date | None,
    today: date | None = None,
    market_is_open: bool = False,
) -> list[DataUpdateTableStatus]:
    """
    Return dynamic status for every table `saham fetch market` may touch.

    The result is scoped to the stock tickers in the current run. Index tickers
    such as ^JKSE are intentionally excluded by the caller for non-candle tables.
    """
    today = today or date.today()
    stock_tickers = [t.upper() for t in tickers if not t.startswith("^")]
    broker_source_value = broker_provider_name

    specs = [
        _TableSpec(
            "candles",
            candles_provider,
            "Daily OHLCV price history",
            "date",
            applicable=not broker_only,
            skipped_reason="--broker-only",
        ),
        _TableSpec(
            "broker_summaries",
            "idx",
            "IDX foreign buy/sell totals + top named brokers",
            "date",
            source_column="source",
            source_value="idx",
            applicable=not candles_only,
            skipped_reason="--candles-only",
        ),
        _TableSpec(
            "foreign_flow_points",
            broker_provider_name,
            "Net foreign flow time series",
            "date",
            source_column="source",
            source_value=broker_source_value,
            applicable=not candles_only,
            skipped_reason="--candles-only",
        ),
        _TableSpec(
            "broker_daily_flow",
            broker_provider_name,
            "Per-broker named buy/sell flow",
            "date",
            source_column="source",
            source_value=broker_source_value,
            applicable=not candles_only and broker_provider_name == "stockbit",
            skipped_reason="provider has no per-broker daily flow",
        ),
        _TableSpec(
            "stock_meta",
            "yahoo",
            "Sector/industry classification",
            "fetched_at",
            freshness="ttl30",
            applicable=not no_meta,
            skipped_reason="--no-meta",
        ),
        _TableSpec(
            "analyst_cache",
            "stockbit",
            "Analyst consensus",
            "fetched_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        _TableSpec(
            "insider_cache",
            "stockbit",
            "Insider transaction cache",
            "fetched_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        _TableSpec(
            "seasonality_cache",
            "stockbit",
            "Monthly seasonality cache",
            "fetched_month",
            freshness="month",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        _TableSpec(
            "corp_action_cache",
            "stockbit",
            "Corporate action cache",
            "fetched_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        _TableSpec(
            "shareholding_composition",
            "stockbit",
            "Shareholding composition",
            "fetched_date",
            freshness="ttl7",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        _TableSpec(
            "bandar_detector",
            "stockbit",
            "Bandar detector snapshot",
            "session_date",
            freshness="today",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
        _TableSpec(
            "company_fundamentals",
            "stockbit",
            "Company fundamental ratios",
            "fetched_date",
            freshness="ttl7",
            applicable=enrichment_available,
            skipped_reason="no Stockbit enrichment",
        ),
    ]

    if not db_path.exists():
        return [
            DataUpdateTableStatus(
                table=spec.table,
                source=spec.source,
                rows=None,
                tickers=None,
                range_label="-",
                status="missing-db",
                contains=spec.contains,
                impact="No SQLite database exists.",
                issue="database file was not created",
            )
            for spec in specs
            if spec.applicable
        ]

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [
            _status_for_spec(
                conn,
                spec,
                stock_tickers,
                expected_trading_day=expected_trading_day,
                today=today,
                market_is_open=market_is_open,
            )
            for spec in specs
        ]


def _status_for_spec(
    conn: sqlite3.Connection,
    spec: _TableSpec,
    tickers: list[str],
    *,
    expected_trading_day: date | None,
    today: date,
    market_is_open: bool = False,
) -> DataUpdateTableStatus:
    if not spec.applicable:
        return DataUpdateTableStatus(
            table=spec.table,
            source=spec.source,
            rows=None,
            tickers=None,
            range_label="-",
            status="skipped",
            contains=spec.contains,
            impact=f"Skipped ({spec.skipped_reason}).",
        )

    if not _table_exists(conn, spec.table):
        return DataUpdateTableStatus(
            table=spec.table,
            source=spec.source,
            rows=0,
            tickers=0,
            range_label="-",
            status="missing",
            contains=spec.contains,
            impact="No rows available for this run.",
            issue=f"{spec.table} table does not exist",
        )

    if not tickers:
        return DataUpdateTableStatus(
            table=spec.table,
            source=spec.source,
            rows=0,
            tickers=0,
            range_label="-",
            status="n/a",
            contains=spec.contains,
            impact="No stock tickers in this run.",
        )

    placeholders = ",".join("?" * len(tickers))
    where = f"ticker IN ({placeholders})"
    params: list[object] = list(tickers)
    if spec.source_column and spec.source_value:
        where += f" AND {spec.source_column} = ?"
        params.append(spec.source_value)

    row = conn.execute(
        f"""
        SELECT COUNT(*) AS rows,
               COUNT(DISTINCT ticker) AS tickers,
               MIN({spec.date_column}) AS min_date,
               MAX({spec.date_column}) AS max_date
        FROM {spec.table}
        WHERE {where}
        """,
        params,
    ).fetchone()

    rows = int(row["rows"] or 0)
    ticker_count = int(row["tickers"] or 0)
    min_raw = row["min_date"]
    max_raw = row["max_date"]
    range_label = _range_label(min_raw, max_raw)
    status, impact, issue = _freshness_status(
        spec,
        rows,
        ticker_count,
        len(tickers),
        max_raw,
        expected_trading_day=expected_trading_day,
        today=today,
        market_is_open=market_is_open,
    )

    return DataUpdateTableStatus(
        table=spec.table,
        source=spec.source,
        rows=rows,
        tickers=ticker_count,
        range_label=range_label,
        status=status,
        contains=spec.contains,
        impact=impact,
        issue=issue,
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _range_label(min_raw: str | None, max_raw: str | None) -> str:
    if not min_raw or not max_raw:
        return "-"
    if min_raw == max_raw:
        return str(max_raw)[:10]
    return f"{str(min_raw)[:10]}..{str(max_raw)[:10]}"


def _freshness_status(
    spec: _TableSpec,
    rows: int,
    ticker_count: int,
    requested_tickers: int,
    max_raw: str | None,
    *,
    expected_trading_day: date | None,
    today: date,
    market_is_open: bool = False,
) -> tuple[str, str, str | None]:
    if rows <= 0:
        return (
            "empty",
            "No rows for requested tickers.",
            f"{spec.table} has no rows for requested tickers",
        )

    partial_issue = None
    if ticker_count < requested_tickers:
        partial_issue = (
            f"{spec.table} has {ticker_count}/{requested_tickers} requested tickers"
        )

    max_date = _parse_dateish(max_raw, spec.freshness)

    if spec.freshness == "range" and expected_trading_day is not None:
        if max_date is None or max_date < expected_trading_day:
            if market_is_open and max_date is not None and (expected_trading_day - max_date).days <= 3:
                return (
                    "pending-eod",
                    f"EOD data not yet published for {expected_trading_day}. Re-fetch after market close (~15:30 WIB).",
                    None,
                )
            return (
                "stale",
                f"Latest stored date is before expected trading day {expected_trading_day}.",
                partial_issue or f"{spec.table} is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", f"Current through {expected_trading_day}.", None

    if spec.freshness == "today":
        if max_date != today:
            return (
                "stale",
                f"Latest fetched date is not today ({today}).",
                partial_issue or f"{spec.table} cache is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", "Fetched today.", None

    if spec.freshness == "month":
        current_month = f"{today.year:04d}-{today.month:02d}"
        if str(max_raw or "") != current_month:
            return (
                "stale",
                f"Latest fetched month is not current month ({current_month}).",
                partial_issue or f"{spec.table} cache is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", "Fetched for current month.", None

    ttl_days = 30 if spec.freshness == "ttl30" else 7 if spec.freshness == "ttl7" else None
    if ttl_days is not None:
        if max_date is None or (today - max_date).days > ttl_days:
            return (
                "stale",
                f"Latest cache is older than {ttl_days}d TTL.",
                partial_issue or f"{spec.table} cache is stale",
            )
        if partial_issue:
            return "partial", "Some requested tickers are missing.", partial_issue
        return "ready", f"Fresh within {ttl_days}d TTL.", None

    if partial_issue:
        return "partial", "Some requested tickers are missing.", partial_issue
    return "ready", "Rows exist for requested tickers.", None


def _parse_dateish(raw: str | None, freshness: str) -> date | None:
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
