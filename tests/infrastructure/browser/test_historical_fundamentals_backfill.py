"""
Tests for historical quarterly backfill from keystats financial_year_parent.

Covers:
  - _parse_financial_value() string parsing
  - _parse_historical_rows() data extraction + derived metric computation
  - _write_historical_rows() INSERT OR IGNORE + 60-day publication lag
  - PIT visibility: data appears at period_end + 60 days, not before
  - Freshness guard: near-future rows are skipped to protect _is_cache_fresh()
  - Real snapshots win over historical rows when they have a later date
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from src.infrastructure.browser.stockbit_fundamentals import (
    StockbitFundamentalsProvider,
    _parse_financial_value,
    _parse_historical_rows,
)

_LAG = timedelta(days=60)
_TTL = timedelta(days=7)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_body(
    net_income_by_year: dict[str, dict[str, str]],
    revenue_by_year: dict[str, dict[str, str]],
) -> dict:
    def _group(fitem_name: str, by_year: dict[str, dict[str, str]]) -> dict:
        year_values = []
        for year, quarters in by_year.items():
            year_values.append(
                {
                    "year": year,
                    "period_values": [
                        {"period": q, "quarter_value": v} for q, v in quarters.items()
                    ],
                }
            )
        return {"fitem_name": fitem_name, "financial_year_values": year_values}

    return {
        "data": {
            "financial_year_parent": {
                "financial_year_groups": [
                    _group("Net Income", net_income_by_year),
                    _group("Revenue", revenue_by_year),
                ]
            },
            "closure_fin_items_results": [],
            "stats": {},
            "info": {},
        }
    }


def _body_for_period_end(period_end: date) -> dict:
    """Build a single-quarter body whose period_end is exactly period_end."""
    _period_map = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
    period = _period_map[period_end.month]
    year = str(period_end.year)
    return _make_body(
        net_income_by_year={year: {period: "200 B"}},
        revenue_by_year={year: {period: "500 B"}},
    )


# ── 1. _parse_financial_value ─────────────────────────────────────────────────


def test_parse_financial_value_handles_billions_and_commas():
    assert _parse_financial_value("14,684 B") == pytest.approx(14684.0)


def test_parse_financial_value_handles_plain_float():
    assert _parse_financial_value("471.10") == pytest.approx(471.10)


def test_parse_financial_value_returns_none_for_dash():
    assert _parse_financial_value("-") is None


def test_parse_financial_value_strips_suffix_without_space():
    assert _parse_financial_value("29654B") == pytest.approx(29654.0)


# ── 2. _parse_historical_rows — structure ─────────────────────────────────────


def test_parse_historical_rows_returns_quarterly_rows():
    body = _make_body(
        net_income_by_year={
            "2024": {"Q1": "100 B", "Q2": "110 B", "Q3": "105 B", "Q4": "120 B"},
            "2025": {"Q1": "115 B", "Q2": "125 B", "Q3": "118 B", "Q4": "130 B"},
        },
        revenue_by_year={
            "2024": {"Q1": "400 B", "Q2": "420 B", "Q3": "410 B", "Q4": "450 B"},
            "2025": {"Q1": "430 B", "Q2": "460 B", "Q3": "440 B", "Q4": "480 B"},
        },
    )
    rows = _parse_historical_rows("BBCA", body)
    assert len(rows) == 8
    dates = {r.fetched_at.strftime("%Y-%m-%d") for r in rows}
    assert "2024-03-31" in dates
    assert "2024-06-30" in dates
    assert "2025-12-31" in dates
    for r in rows:
        assert r.net_profit_margin is not None
        assert r.piotroski_f_score is None
        assert r.market_cap_idr is None
        assert r.roe_ttm is None


# ── 3. Revenue YoY growth computation ────────────────────────────────────────


def test_parse_historical_rows_computes_revenue_yoy_growth_correctly():
    body = _make_body(
        net_income_by_year={"2024": {"Q1": "100 B"}, "2025": {"Q1": "110 B"}},
        revenue_by_year={"2024": {"Q1": "400 B"}, "2025": {"Q1": "440 B"}},
    )
    rows = _parse_historical_rows("BBCA", body)
    q1_2025 = next(r for r in rows if r.fetched_at.year == 2025 and r.fetched_at.month == 3)
    assert q1_2025.revenue_yoy_growth == pytest.approx(10.0, abs=0.01)


def test_parse_historical_rows_yoy_growth_none_when_no_prior_year():
    body = _make_body(
        net_income_by_year={"2025": {"Q1": "100 B"}},
        revenue_by_year={"2025": {"Q1": "400 B"}},
    )
    rows = _parse_historical_rows("BBCA", body)
    assert len(rows) == 1
    assert rows[0].revenue_yoy_growth is None


# ── 4. Net profit margin computation ─────────────────────────────────────────


def test_parse_historical_rows_computes_net_profit_margin_correctly():
    body = _make_body(
        net_income_by_year={"2024": {"Q1": "200 B"}},
        revenue_by_year={"2024": {"Q1": "500 B"}},
    )
    rows = _parse_historical_rows("BBCA", body)
    assert rows[0].net_profit_margin == pytest.approx(40.0, abs=0.01)


# ── 5. INSERT OR IGNORE semantics ────────────────────────────────────────────


def test_write_historical_rows_uses_insert_or_ignore(tmp_path):
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)

    # Use a period_end safely in the past (> 60 + 7 days ago)
    period_end = date.today() - timedelta(days=70)
    # Snap to a valid quarter-end
    period_end = date(period_end.year, 3, 31)
    body = _body_for_period_end(period_end)
    rows = _parse_historical_rows("BBCA", body)
    assert len(rows) == 1

    prov._write_historical_rows(rows)
    prov._write_historical_rows(rows)  # second write must be ignored

    with sqlite3.connect(str(db)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM company_fundamentals WHERE ticker='BBCA'"
        ).fetchone()[0]
    assert count == 1


# ── 6. PIT visibility: available after period_end + 60 days ──────────────────


def test_historical_row_visible_after_publication_lag(tmp_path):
    """Data becomes visible at period_end + 60 days, not at period_end."""
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)

    period_end = date(2024, 3, 31)  # Q1 2024
    body = _body_for_period_end(period_end)
    prov._write_historical_rows(_parse_historical_rows("BBCA", body))

    available = period_end + _LAG  # 2024-05-30

    # One day before available → not visible
    result_before = prov.get_fundamentals("BBCA", as_of_date=available - timedelta(days=1))
    assert result_before is None

    # On available date → visible
    result_on = prov.get_fundamentals("BBCA", as_of_date=available)
    assert result_on is not None
    assert result_on.net_profit_margin == pytest.approx(40.0, abs=0.01)


# ── 7. Freshness guard: near-future/recent rows are skipped ──────────────────


def test_recent_quarter_skipped_to_protect_freshness_check(tmp_path):
    """A quarter whose available_date is within TTL window must not be written."""
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)

    # available_date = today → within TTL → must be skipped
    too_recent_period_end = date.today() - _LAG
    # Snap to nearest valid quarter-end in the past
    month = too_recent_period_end.month
    quarter_month = (((month - 1) // 3) * 3) + 3
    too_recent_period_end = date(too_recent_period_end.year, quarter_month,
                                  31 if quarter_month in (3, 12) else 30)
    body = _body_for_period_end(too_recent_period_end)
    prov._write_historical_rows(_parse_historical_rows("BBCA", body))

    with sqlite3.connect(str(db)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM company_fundamentals WHERE ticker='BBCA'"
        ).fetchone()[0]
    assert count == 0, "Near-future available_date must not be written to PIT table"


# ── 8. Real snapshot wins over historical row ─────────────────────────────────


def test_real_snapshot_wins_over_historical_row(tmp_path):
    """A real snapshot (full timestamp, later date) always beats a historical row."""
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)

    period_end = date(2024, 3, 31)  # Q1 2024 → available 2024-05-30
    body = _body_for_period_end(period_end)
    prov._write_historical_rows(_parse_historical_rows("BBCA", body))

    # Real snapshot taken after the historical available date
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO company_fundamentals "
            "(ticker, fetched_date, net_profit_margin, piotroski_f_score) VALUES (?,?,?,?)",
            ("BBCA", "2024-07-01T09:00:00", 42.0, 7),
        )

    # as_of July 15 → real snapshot (Jul 1) wins over historical (May 30)
    result = prov.get_fundamentals("BBCA", as_of_date=date(2024, 7, 15))
    assert result is not None
    assert result.piotroski_f_score == 7
    assert result.net_profit_margin == pytest.approx(42.0)
