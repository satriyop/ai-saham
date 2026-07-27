"""
SQLite reader for point-in-time enrichment coverage.

Queries each enrichment cache table to report how many distinct snapshot dates
and tickers are stored, enabling the CLI to show PIT history depth.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from src.application.use_case.fetch_enrichment_history_use_case import (
    EnrichmentPitTableCoverage,
)

logger = logging.getLogger(__name__)

_PIT_TABLES: tuple[tuple[str, str], ...] = (
    ("company_fundamentals", "date(fetched_date)"),
    ("shareholding_composition", "date(fetched_date)"),
    ("analyst_cache", "date(fetched_date)"),
    ("ticker_notation_cache", "date(fetched_date)"),
    ("forward_estimates_cache", "date(fetched_date)"),
    ("stock_meta", "date(substr(fetched_at,1,10))"),
    ("company_profile_cache", "date(substr(fetched_date,1,10))"),
    (
        "seasonality_cache",
        "date(COALESCE(substr(fetched_at,1,10), fetched_month || '-01'))",
    ),
    ("earnings_cache", "date(substr(fetched_date,1,10))"),
)


def read_enrichment_pit_coverage(db_path: Path) -> list[EnrichmentPitTableCoverage]:
    """Return per-table PIT coverage rows for all enrichment cache tables."""
    rows: list[EnrichmentPitTableCoverage] = []
    for table, date_expr in _PIT_TABLES:
        try:
            with sqlite3.connect(str(db_path)) as conn:
                agg = conn.execute(
                    f"SELECT COUNT(DISTINCT {date_expr}), MAX({date_expr}) FROM {table}"
                ).fetchone()
                snap_count = int(agg[0]) if agg and agg[0] else 0
                latest_date = agg[1] if agg else None
                ticker_count = 0
                if latest_date:
                    ticker_count = (
                        conn.execute(
                            f"SELECT COUNT(DISTINCT ticker) FROM {table} WHERE {date_expr} = ?",
                            (latest_date,),
                        ).fetchone()[0]
                        or 0
                    )
        except Exception as exc:
            logger.debug("enrichment_pit_coverage: %s unavailable: %s", table, exc)
            snap_count, latest_date, ticker_count = 0, None, 0
        rows.append(
            EnrichmentPitTableCoverage(
                table=table,
                snapshot_count=snap_count,
                latest_date=latest_date,
                tickers_in_latest=ticker_count,
            )
        )
    return rows
