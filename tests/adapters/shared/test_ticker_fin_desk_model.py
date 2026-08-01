"""Ticker financials desk — three cards, design hero, honest empty."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.adapters.shared.ticker_fin_desk_model import build_ticker_fin_desk_model
from src.adapters.shared.view_ticker_job_text import format_ticker_financials_job


def _period(**kw: object) -> SimpleNamespace:
    base = dict(
        period_end=date(2026, 3, 31),
        total_revenue=28.6e12,
        net_income=14.6e12,
        eps_basic=119.0,
        total_assets=None,
        stockholders_equity=None,
        total_debt=None,
        operating_cash_flow=None,
        free_cash_flow=None,
        capital_expenditure=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_fin_desk_three_cards_hero_from_income():
    results = (
        SimpleNamespace(
            statement="income",
            period_type="quarter",
            status="ok",
            source="yahoo",
            periods=(
                _period(),
                _period(period_end=date(2025, 12, 31), total_revenue=26e12, net_income=14e12),
            ),
            message=None,
        ),
        SimpleNamespace(
            statement="balance",
            period_type="quarter",
            status="ok",
            source="yahoo",
            periods=(
                _period(
                    total_revenue=None,
                    net_income=None,
                    eps_basic=None,
                    total_assets=1.64e15,
                    stockholders_equity=3e14,
                    total_debt=1e14,
                ),
            ),
            message=None,
        ),
        SimpleNamespace(
            statement="cashflow",
            period_type="quarter",
            status="empty",
            source="yahoo",
            periods=(),
            message="No cashflow periods cached",
        ),
    )
    desk = build_ticker_fin_desk_model("BBCA", results)
    assert desk.empty is False
    assert desk.hero_lab == "FINANCIALS"
    assert desk.hero_big == "Q1 2026"
    assert "yahoo" in desk.hero_sub
    assert desk.cards[0].kind == "income" and desk.cards[0].status == "ok"
    assert desk.cards[0].rows[0].label == "Revenue"
    assert desk.cards[1].kind == "balance" and desk.cards[1].status == "ok"
    assert desk.cards[2].kind == "cashflow" and desk.cards[2].status == "empty"
    assert desk.pulses[3].value == "2/3"
    text = format_ticker_financials_job("BBCA", results)
    assert text.desk is not None
    assert text.job == "fin"


def test_fin_desk_annual_fy_label_and_hero_sub():
    results = (
        SimpleNamespace(
            statement="income",
            period_type="annual",
            status="ok",
            source="yahoo",
            periods=(_period(period_end=date(2025, 12, 31)),),
            message=None,
        ),
        SimpleNamespace(
            statement="balance",
            period_type="annual",
            status="ok",
            source="yahoo",
            periods=(
                _period(
                    period_end=date(2025, 12, 31),
                    total_revenue=None,
                    net_income=None,
                    eps_basic=None,
                    total_assets=1e15,
                    stockholders_equity=2e14,
                    total_debt=5e13,
                ),
            ),
            message=None,
        ),
        SimpleNamespace(
            statement="cashflow",
            period_type="annual",
            status="empty",
            source="yahoo",
            periods=(),
            message="No cashflow periods cached",
        ),
    )
    desk = build_ticker_fin_desk_model("BBCA", results)
    assert desk.hero_big == "FY 2025"
    assert desk.hero_sub.startswith("annual")
    assert desk.cards[0].period_label == "FY 2025"
    assert "y period" in desk.footer
    text = format_ticker_financials_job("BBCA", results)
    assert "INCOME" in text.body
    assert "BALANCE" in text.body


def test_fin_desk_all_empty_honest():
    desk = build_ticker_fin_desk_model("UNVR", ())
    assert desk.empty is True
    assert desk.hero_big == "—"
    assert all(c.status == "empty" for c in desk.cards)
