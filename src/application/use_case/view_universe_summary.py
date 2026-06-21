"""
Universe view use case.

Aggregates locally cached market data (candles, broker flow, stock meta) across
all tickers in a named universe. Uses direct sqlite3 queries rather than entity
hydration — avoids per-object overhead for 45–600+ tickers.

Layer: Application
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.services.universe_loader import (
    UNIVERSE_CONFIG_PATH,
    UniverseNotFoundError,
    load_universe_entry,
)


@dataclass
class UniverseTickerRow:
    ticker: str
    name: str | None
    sector: str | None
    last_close: Decimal | None
    change_pct: float | None
    volume: int | None
    foreign_net_value: Decimal | None
    foreign_flow_ratio: float | None
    latest_date: date | None


@dataclass
class UniverseViewResult:
    universe_name: str
    ticker_count: int
    updated: str
    as_of_date: date | None
    rows: list[UniverseTickerRow]
    missing_candles: int
    missing_flow: int


def build_universe_view(
    universe_name: str,
    db_path: Path,
    config_path: Path = UNIVERSE_CONFIG_PATH,
    as_of_date: date | None = None,
) -> UniverseViewResult:
    """Aggregate locally cached data for all tickers in a named universe.

    Runs three batch SQL queries (candles, broker flow, stock meta) and
    joins the results in Python. Returns lightweight dataclasses — no entity
    hydration.

    Raises:
        UniverseNotFoundError: If universe_name is not in config.
        FileNotFoundError: If universes.yaml does not exist.
    """
    tickers, updated = load_universe_entry(universe_name, config_path)

    if not tickers:
        return UniverseViewResult(
            universe_name=universe_name,
            ticker_count=0,
            updated=updated,
            as_of_date=None,
            rows=[],
            missing_candles=0,
            missing_flow=0,
        )

    sorted_tickers = sorted(tickers)

    if not db_path.exists():
        return UniverseViewResult(
            universe_name=universe_name,
            ticker_count=len(sorted_tickers),
            updated=updated,
            as_of_date=None,
            rows=[
                UniverseTickerRow(
                    ticker=t,
                    name=None,
                    sector=None,
                    last_close=None,
                    change_pct=None,
                    volume=None,
                    foreign_net_value=None,
                    foreign_flow_ratio=None,
                    latest_date=None,
                )
                for t in sorted_tickers
            ],
            missing_candles=len(sorted_tickers),
            missing_flow=len(sorted_tickers),
        )

    ph = ",".join("?" * len(sorted_tickers))
    date_ceil = as_of_date.isoformat() if as_of_date else None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        candle_rows = _query_candles(conn, sorted_tickers, ph, date_ceil)
        broker_rows = _query_broker(conn, sorted_tickers, ph, date_ceil)
        meta_rows = conn.execute(
            f"SELECT ticker, name, sector FROM stock_meta WHERE ticker IN ({ph})",
            sorted_tickers,
        ).fetchall()
    finally:
        conn.close()

    return _assemble(
        universe_name=universe_name,
        sorted_tickers=sorted_tickers,
        updated=updated,
        candle_rows=candle_rows,
        broker_rows=broker_rows,
        meta_rows=meta_rows,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _query_candles(
    conn: sqlite3.Connection,
    tickers: list[str],
    ph: str,
    date_ceil: str | None,
) -> list:
    """Latest 2 trading dates of candle data per ticker (for price + change%).

    Pre-computes MAX(date) as a scalar to avoid repeating the tickers bind params
    inside a correlated subquery.
    """
    ceil_clause = "AND date <= ? " if date_ceil else ""
    ceil_params = [date_ceil] if date_ceil else []

    max_row = conn.execute(
        f"SELECT MAX(date) FROM candles WHERE ticker IN ({ph}) {ceil_clause}",
        tickers + ceil_params,
    ).fetchone()
    max_date = max_row[0] if max_row else None
    if not max_date:
        return []

    return conn.execute(
        f"""
        SELECT ticker, date, close, volume FROM candles
        WHERE ticker IN ({ph})
          {ceil_clause}
          AND date >= DATE(?, '-10 days')
        ORDER BY ticker, date DESC
        """,
        tickers + ceil_params + [max_date],
    ).fetchall()


def _query_broker(
    conn: sqlite3.Connection,
    tickers: list[str],
    ph: str,
    date_ceil: str | None,
) -> list:
    """Latest broker summary per ticker (foreign buy/sell + total value).

    The JOIN already constrains to matched tickers so the outer WHERE is omitted,
    halving the number of bind params.
    """
    ceil_clause = "AND date <= ? " if date_ceil else ""
    params = tickers + ([date_ceil] if date_ceil else [])
    return conn.execute(
        f"""
        SELECT b.ticker, b.date, b.foreign_buy_value, b.foreign_sell_value,
               b.total_value, b.total_lot
        FROM broker_summaries b
        JOIN (
            SELECT ticker, MAX(date) AS max_date
            FROM broker_summaries
            WHERE ticker IN ({ph}) {ceil_clause}
            GROUP BY ticker
        ) latest ON b.ticker = latest.ticker AND b.date = latest.max_date
        ORDER BY b.ticker
        """,
        params,
    ).fetchall()


def _assemble(
    *,
    universe_name: str,
    sorted_tickers: list[str],
    updated: str,
    candle_rows: list,
    broker_rows: list,
    meta_rows: list,
) -> UniverseViewResult:
    """Join three result sets in Python and build UniverseViewResult."""
    candle_map: dict[str, list[tuple[str, Decimal, int]]] = defaultdict(list)
    for row in candle_rows:
        candle_map[row["ticker"]].append((row["date"], Decimal(row["close"]), row["volume"]))

    # First row per ticker wins (query returns one row per ticker via MAX(date) JOIN)
    broker_map: dict[str, tuple[Decimal, float | None]] = {}
    for row in broker_rows:
        t = row["ticker"]
        if t in broker_map:
            continue
        buy = Decimal(row["foreign_buy_value"])
        sell = Decimal(row["foreign_sell_value"])
        net = buy - sell
        total = Decimal(row["total_value"])
        ratio = float(net / total * 100) if total > 0 else None
        broker_map[t] = (net, ratio)

    meta_map: dict[str, tuple[str | None, str | None]] = {
        row["ticker"]: (row["name"], row["sector"])
        for row in meta_rows
    }

    # Overall as_of_date = most common latest candle date across the universe
    latest_dates = [rows[0][0] for rows in candle_map.values() if rows]
    as_of_date: date | None = None
    if latest_dates:
        most_common_str = Counter(latest_dates).most_common(1)[0][0]
        try:
            as_of_date = date.fromisoformat(most_common_str)
        except ValueError:
            pass

    rows: list[UniverseTickerRow] = []
    missing_candles = 0
    missing_flow = 0

    for ticker in sorted_tickers:
        ticker_candles = candle_map.get(ticker, [])
        name, sector = meta_map.get(ticker, (None, None))

        last_close: Decimal | None = None
        change_pct: float | None = None
        volume: int | None = None
        latest_date: date | None = None

        if ticker_candles:
            latest_date_str, last_close, volume = ticker_candles[0]
            try:
                latest_date = date.fromisoformat(latest_date_str)
            except ValueError:
                pass
            if len(ticker_candles) >= 2:
                prev_close = ticker_candles[1][1]
                if prev_close > 0:
                    change_pct = float((last_close - prev_close) / prev_close * 100)
        else:
            missing_candles += 1

        flow = broker_map.get(ticker)
        if flow is not None:
            foreign_net_value, foreign_flow_ratio = flow
        else:
            foreign_net_value = foreign_flow_ratio = None
            missing_flow += 1

        rows.append(
            UniverseTickerRow(
                ticker=ticker,
                name=name,
                sector=sector,
                last_close=last_close,
                change_pct=change_pct,
                volume=volume,
                foreign_net_value=foreign_net_value,
                foreign_flow_ratio=foreign_flow_ratio,
                latest_date=latest_date,
            )
        )

    return UniverseViewResult(
        universe_name=universe_name,
        ticker_count=len(sorted_tickers),
        updated=updated,
        as_of_date=as_of_date,
        rows=rows,
        missing_candles=missing_candles,
        missing_flow=missing_flow,
    )
