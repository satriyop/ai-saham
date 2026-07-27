"""Unit tests for YahooFinancialsProvider mapping (no live network)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.infrastructure.data_providers.yahoo_financials import YahooFinancialsProvider


class _FakeTicker:
    def __init__(self, quarterly, annual, info=None):
        self.quarterly_income_stmt = quarterly
        self.income_stmt = annual
        self.info = info or {"financialCurrency": "IDR"}


def test_maps_quarterly_and_annual_line_items(monkeypatch):
    q = pd.DataFrame(
        {
            datetime(2026, 3, 31): {
                "Total Revenue": 28_660_037_000_000.0,
                "Net Income Common Stockholders": 14_684_123_000_000.0,
                "Net Income Including Noncontrolling Interests": 14_689_799_000_000.0,
                "Interest Income": 24_387_580_000_000.0,
                "Basic EPS": 119.0,
                "Diluted EPS": 119.0,
            },
            datetime(2025, 12, 31): {
                "Total Revenue": 26_715_069_000_000.0,
                "Net Income Common Stockholders": 14_139_872_000_000.0,
                "Net Income Including Noncontrolling Interests": 14_149_630_000_000.0,
                "Interest Income": 24_731_161_000_000.0,
                "Basic EPS": float("nan"),
                "Diluted EPS": float("nan"),
            },
        }
    )
    a = pd.DataFrame(
        {
            datetime(2025, 12, 31): {
                "Total Revenue": 100.0,
                "Net Income": 50.0,
                "Net Income Including Noncontrolling Interests": 51.0,
                "Interest Income": 40.0,
                "Basic EPS": 1.5,
                "Diluted EPS": 1.4,
            }
        }
    )

    monkeypatch.setattr(
        "src.infrastructure.data_providers.yahoo_financials.yf.Ticker",
        lambda sym: _FakeTicker(q, a),
    )

    provider = YahooFinancialsProvider(market_suffix=".JK")
    periods = provider.fetch_statements("bbca")

    assert {p.period_type for p in periods} == {"quarter", "annual"}
    q1 = next(p for p in periods if p.period_end.isoformat() == "2026-03-31")
    assert q1.source == "yahoo"
    assert q1.currency == "IDR"
    assert q1.total_revenue == 28_660_037_000_000
    assert q1.net_income == 14_684_123_000_000
    assert q1.net_income_incl_nci == 14_689_799_000_000
    assert q1.interest_income == 24_387_580_000_000
    assert q1.eps_basic == 119.0
    assert q1.eps_diluted == 119.0

    q_nan = next(
        p
        for p in periods
        if p.period_end.isoformat() == "2025-12-31" and p.period_type == "quarter"
    )
    assert q_nan.eps_basic is None
    assert q_nan.eps_diluted is None

    ann = next(p for p in periods if p.period_type == "annual")
    assert ann.net_income == 50
    assert ann.eps_diluted == 1.4


def test_empty_frames_return_empty_list(monkeypatch):
    empty = pd.DataFrame()
    monkeypatch.setattr(
        "src.infrastructure.data_providers.yahoo_financials.yf.Ticker",
        lambda sym: _FakeTicker(empty, empty),
    )
    provider = YahooFinancialsProvider(market_suffix=".JK")
    assert provider.fetch_statements("BBCA") == []
