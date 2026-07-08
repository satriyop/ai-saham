"""
Tests for historical quarterly backfill from keystats financial_year_parent.

Covers:
  - _parse_financial_value() string parsing
  - _parse_historical_rows() data extraction + derived metric computation
  - _write_historical_rows() INSERT OR IGNORE semantics
  - Isolation: historical rows go to company_fundamentals_history, NOT to the
    PIT table (company_fundamentals), so get_fundamentals() is unaffected.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from src.infrastructure.browser.stockbit_fundamentals import (
    StockbitFundamentalsProvider,
    _parse_financial_value,
    _parse_historical_rows,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_body(
    net_income_by_year: dict[str, dict[str, str]],
    revenue_by_year: dict[str, dict[str, str]],
) -> dict:
    """Build a minimal keystats body with financial_year_parent populated."""

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


# ── 3. Revenue YoY growth computation ─────────────────────────────────────────


def test_parse_historical_rows_computes_revenue_yoy_growth_correctly():
    body = _make_body(
        net_income_by_year={"2024": {"Q1": "100 B"}, "2025": {"Q1": "110 B"}},
        revenue_by_year={"2024": {"Q1": "400 B"}, "2025": {"Q1": "440 B"}},
    )
    rows = _parse_historical_rows("BBCA", body)
    q1_2025 = next(r for r in rows if r.fetched_at.year == 2025 and r.fetched_at.month == 3)
    # (440 - 400) / 400 * 100 = 10.0
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
    assert len(rows) == 1
    # 200 / 500 * 100 = 40.0
    assert rows[0].net_profit_margin == pytest.approx(40.0, abs=0.01)


# ── 5. INSERT OR IGNORE semantics (targets history table) ────────────────────


def test_write_historical_rows_uses_insert_or_ignore(tmp_path):
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)

    body = _make_body(
        net_income_by_year={"2024": {"Q1": "100 B"}},
        revenue_by_year={"2024": {"Q1": "400 B"}},
    )
    rows = _parse_historical_rows("BBCA", body)
    assert len(rows) == 1

    # Write twice — second write should be ignored due to UNIQUE(ticker, period_end_date)
    prov._write_historical_rows(rows)
    prov._write_historical_rows(rows)

    with sqlite3.connect(str(db)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM company_fundamentals_history WHERE ticker='BBCA'"
        ).fetchone()[0]
    assert count == 1


# ── 6. Historical rows are isolated from PIT reads ────────────────────────────


def test_historical_rows_go_to_history_table_not_pit_table(tmp_path):
    """Historical rows must NOT appear in company_fundamentals (the PIT table)."""
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)

    body = _make_body(
        net_income_by_year={"2024": {"Q1": "200 B"}},
        revenue_by_year={"2024": {"Q1": "500 B"}},
    )
    prov._write_historical_rows(_parse_historical_rows("BBCA", body))

    with sqlite3.connect(str(db)) as conn:
        pit_count = conn.execute(
            "SELECT COUNT(*) FROM company_fundamentals WHERE ticker='BBCA'"
        ).fetchone()[0]
        hist_count = conn.execute(
            "SELECT COUNT(*) FROM company_fundamentals_history WHERE ticker='BBCA'"
        ).fetchone()[0]

    assert pit_count == 0, "PIT table must not contain derived historical rows"
    assert hist_count == 1


def test_get_fundamentals_does_not_read_from_history_table(tmp_path):
    """get_fundamentals() with as_of_date returns None when only history rows exist."""
    db = tmp_path / "test.db"
    prov = StockbitFundamentalsProvider(api_client=None, db_path=db)

    body = _make_body(
        net_income_by_year={"2024": {"Q1": "200 B"}},
        revenue_by_year={"2024": {"Q1": "500 B"}},
    )
    prov._write_historical_rows(_parse_historical_rows("BBCA", body))

    # Even though we have historical data for Q1 2024, PIT read must return None
    # because the data was never confirmed available on any specific date.
    result = prov.get_fundamentals("BBCA", as_of_date=date(2024, 6, 1))
    assert result is None
