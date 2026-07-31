"""Pure formatters for ticker jobs — multi-surface contract (not stubs)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.shared.view_ticker_job_text import (
    empty_ticker_job,
    format_ticker_distribution_job,
    format_ticker_financials_job,
    format_ticker_flow_job,
    format_ticker_foreign_history_job,
)


def test_format_ticker_flow_job_rows_from_summaries():
    summaries = (
        SimpleNamespace(
            date=date(2026, 7, 28),
            foreign_net_value=Decimal("-1000000000"),
            foreign_flow_ratio=Decimal("12.5"),
            is_foreign_accumulating=False,
            top_buyers=(SimpleNamespace(broker_code="YP"),),
            top_sellers=(SimpleNamespace(broker_code="AK"),),
        ),
        SimpleNamespace(
            date=date(2026, 7, 29),
            foreign_net_value=Decimal("500000000"),
            foreign_flow_ratio=Decimal("8.0"),
            is_foreign_accumulating=True,
            top_buyers=(SimpleNamespace(broker_code="CC"),),
            top_sellers=(),
        ),
    )
    text = format_ticker_flow_job(
        "bbca",
        summaries,
        total_net=Decimal("-500000000"),
        buy_days=1,
        sell_days=1,
        fetch_hint="saham fetch market BBCA",
    )
    assert text.job == "flow"
    assert text.ticker == "BBCA"
    assert text.empty is False
    assert "Foreign flow" in text.body
    assert "2026-07-29" in text.body
    assert "view ticker flow" in text.cli_verb
    assert "ships later" not in text.body.lower()
    assert "Full table paint ships" not in text.body


def test_format_ticker_foreign_history_job():
    points = (
        SimpleNamespace(
            date=date(2026, 7, 29),
            source="stockbit",
            net_val=Decimal("-27800000000"),
            net_lot=-1000,
            avg_price=Decimal("6275"),
        ),
    )
    text = format_ticker_foreign_history_job("BBCA", points, resolved_source="stockbit")
    assert text.job == "foreign"
    assert text.empty is False
    assert "Foreign history" in text.body
    assert "stockbit" in text.body
    assert "foreign-history" in text.cli_verb


def test_format_ticker_distribution_job():
    snap = SimpleNamespace(
        date=date(2026, 7, 29),
        foreign_buying_from_domestic=True,
        net_foreign_buyer_dominance=False,
        top_buyers=(
            SimpleNamespace(
                broker_code="YP",
                broker_type="asing",
                amount_idr=1_200_000_000,
                counterparties=(
                    SimpleNamespace(
                        broker_code="XL",
                        broker_type="lokal",
                        amount_idr=400_000_000,
                    ),
                ),
            ),
        ),
        top_sellers=(),
    )
    text = format_ticker_distribution_job("BBCA", snap)
    assert text.job == "dist"
    assert text.empty is False
    assert "TOP BUYERS" in text.body
    assert "YP" in text.body
    assert "distribution" in text.cli_verb


def test_format_ticker_financials_job_multi_statement():
    period = SimpleNamespace(
        period_end=date(2026, 3, 31),
        total_revenue=1e12,
        net_income=5e11,
        eps_basic=119.1,
        total_assets=2e12,
        stockholders_equity=1e12,
        total_debt=1e11,
        operating_cash_flow=3e11,
        free_cash_flow=2e11,
        capital_expenditure=-1e10,
        source="yahoo",
    )
    results = (
        SimpleNamespace(
            statement="income",
            period_type="quarter",
            status="ok",
            periods=(period,),
            source="yahoo",
            message=None,
            fetch_hint="saham fetch financials BBCA",
        ),
        SimpleNamespace(
            statement="balance",
            period_type="quarter",
            status="ok",
            periods=(period,),
            source="yahoo",
            message=None,
            fetch_hint="saham fetch financials BBCA",
        ),
        SimpleNamespace(
            statement="cashflow",
            period_type="quarter",
            status="empty",
            periods=(),
            source="yahoo",
            message="No cashflow periods",
            fetch_hint="saham fetch financials BBCA",
        ),
    )
    text = format_ticker_financials_job("BBCA", results)
    assert text.job == "fin"
    assert text.empty is False  # income/balance ok
    assert "Income" in text.body or "income" in text.body.lower()
    assert "119.10" in text.body or "119.1" in text.body
    assert "financials" in text.cli_verb


def test_empty_ticker_job_honest():
    text = empty_ticker_job("flow", "GOTO")
    assert text.empty is True
    assert "GOTO" in text.body
    assert "fetch" in text.body.lower() or "Hint" in text.body
    assert "ships later" not in text.body.lower()
