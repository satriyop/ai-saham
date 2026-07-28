"""Unit tests for YahooFinancialsProvider mapping (no live network)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.infrastructure.data_providers.yahoo_financials import YahooFinancialsProvider


class _FakeTicker:
    def __init__(self, frames: dict, info=None):
        self._frames = frames
        self.info = info or {"financialCurrency": "IDR"}

    def __getattr__(self, name: str):
        if name in self._frames:
            return self._frames[name]
        raise AttributeError(name)


def test_maps_income_balance_and_cashflow(monkeypatch):
    q_income = pd.DataFrame(
        {
            datetime(2026, 3, 31): {
                "Total Revenue": 28_660_037_000_000.0,
                "Net Income Common Stockholders": 14_684_123_000_000.0,
                "Net Income Including Noncontrolling Interests": 14_689_799_000_000.0,
                "Interest Income": 24_387_580_000_000.0,
                "Basic EPS": 119.0,
                "Diluted EPS": 119.0,
            }
        }
    )
    q_bs = pd.DataFrame(
        {
            datetime(2026, 3, 31): {
                "Total Assets": 1_640_830_566_000_000.0,
                "Total Liabilities Net Minority Interest": 1_381_471_773_000_000.0,
                "Stockholders Equity": 259_132_407_000_000.0,
                "Cash And Cash Equivalents": 119_676_890_000_000.0,
                "Total Debt": 2_310_155_000_000.0,
            }
        }
    )
    q_cf = pd.DataFrame(
        {
            datetime(2026, 3, 31): {
                "Operating Cash Flow": 47_920_728_000_000.0,
                "Investing Cash Flow": -16_987_375_000_000.0,
                "Financing Cash Flow": -1_072_636_000_000.0,
                "Free Cash Flow": 47_485_515_000_000.0,
                "Capital Expenditure": -435_213_000_000.0,
                "End Cash Position": 117_065_497_000_000.0,
            }
        }
    )
    empty = pd.DataFrame()

    frames = {
        "quarterly_income_stmt": q_income,
        "income_stmt": empty,
        "quarterly_balance_sheet": q_bs,
        "balance_sheet": empty,
        "quarterly_cashflow": q_cf,
        "cashflow": empty,
    }
    monkeypatch.setattr(
        "src.infrastructure.data_providers.yahoo_financials.yf.Ticker",
        lambda sym: _FakeTicker(frames),
    )

    provider = YahooFinancialsProvider(market_suffix=".JK")
    periods = provider.fetch_statements(
        "bbca",
        statement_kinds=frozenset({"income", "balance", "cashflow"}),
    )

    kinds = {p.statement_kind for p in periods}
    assert kinds == {"income", "balance", "cashflow"}

    income = next(p for p in periods if p.statement_kind == "income")
    assert income.total_revenue == 28_660_037_000_000
    assert income.net_income_incl_nci == 14_689_799_000_000
    assert income.total_assets is None

    balance = next(p for p in periods if p.statement_kind == "balance")
    assert balance.total_assets == 1_640_830_566_000_000
    assert balance.net_income is None

    cashflow = next(p for p in periods if p.statement_kind == "cashflow")
    assert cashflow.operating_cash_flow == 47_920_728_000_000
    assert cashflow.free_cash_flow == 47_485_515_000_000


def test_empty_frames_return_empty_list(monkeypatch):
    empty = pd.DataFrame()
    frames = {
        "quarterly_income_stmt": empty,
        "income_stmt": empty,
        "quarterly_balance_sheet": empty,
        "balance_sheet": empty,
        "quarterly_cashflow": empty,
        "cashflow": empty,
    }
    monkeypatch.setattr(
        "src.infrastructure.data_providers.yahoo_financials.yf.Ticker",
        lambda sym: _FakeTicker(frames),
    )
    provider = YahooFinancialsProvider(market_suffix=".JK")
    assert (
        provider.fetch_statements(
            "BBCA", statement_kinds=frozenset({"income", "balance", "cashflow"})
        )
        == []
    )


def test_nan_eps_becomes_none(monkeypatch):
    q = pd.DataFrame(
        {
            datetime(2025, 12, 31): {
                "Total Revenue": 1.0,
                "Net Income": 2.0,
                "Net Income Including Noncontrolling Interests": 2.0,
                "Basic EPS": float("nan"),
                "Diluted EPS": float("nan"),
            }
        }
    )
    empty = pd.DataFrame()
    frames = {
        "quarterly_income_stmt": q,
        "income_stmt": empty,
        "quarterly_balance_sheet": empty,
        "balance_sheet": empty,
        "quarterly_cashflow": empty,
        "cashflow": empty,
    }
    monkeypatch.setattr(
        "src.infrastructure.data_providers.yahoo_financials.yf.Ticker",
        lambda sym: _FakeTicker(frames),
    )
    periods = YahooFinancialsProvider(market_suffix=".JK").fetch_statements(
        "BBCA", statement_kinds=frozenset({"income"})
    )
    assert len(periods) == 1
    assert periods[0].eps_basic is None
    assert periods[0].eps_diluted is None
