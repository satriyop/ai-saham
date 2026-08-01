"""Fin job desk · three cards under ticker chip bar."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from textual.app import App, ComposeResult

from src.adapters.shared.ticker_fin_desk_model import build_ticker_fin_desk_model
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def test_fin_three_cards_painted():
    async def scenario() -> None:
        class _A(App):
            def compose(self) -> ComposeResult:
                yield TickerDesk(id="ticker-desk")

        results = (
            SimpleNamespace(
                statement="income",
                period_type="quarter",
                status="ok",
                source="yahoo",
                periods=(
                    SimpleNamespace(
                        period_end=date(2026, 3, 31),
                        total_revenue=28e12,
                        net_income=14e12,
                        eps_basic=119.0,
                        total_assets=None,
                        stockholders_equity=None,
                        total_debt=None,
                        operating_cash_flow=None,
                        free_cash_flow=None,
                        capital_expenditure=None,
                    ),
                ),
                message=None,
            ),
            SimpleNamespace(
                statement="balance",
                period_type="quarter",
                status="ok",
                source="yahoo",
                periods=(
                    SimpleNamespace(
                        period_end=date(2026, 3, 31),
                        total_revenue=None,
                        net_income=None,
                        eps_basic=None,
                        total_assets=1.6e15,
                        stockholders_equity=3e14,
                        total_debt=1e14,
                        operating_cash_flow=None,
                        free_cash_flow=None,
                        capital_expenditure=None,
                    ),
                ),
                message=None,
            ),
            SimpleNamespace(
                statement="cashflow",
                period_type="quarter",
                status="ok",
                source="yahoo",
                periods=(
                    SimpleNamespace(
                        period_end=date(2026, 3, 31),
                        total_revenue=None,
                        net_income=None,
                        eps_basic=None,
                        total_assets=None,
                        stockholders_equity=None,
                        total_debt=None,
                        operating_cash_flow=47e12,
                        free_cash_flow=40e12,
                        capital_expenditure=-5e12,
                    ),
                ),
                message=None,
            ),
        )
        desk_model = build_ticker_fin_desk_model("BBCA", results)
        app = _A()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            td = app.query_one("#ticker-desk", TickerDesk)
            model = build_ticker_desk_model_from_text(ticker="BBCA", body="Close: 1")
            td.paint(model, detail_open=False)
            td.set_job_view(
                "fin",
                title=desk_model.title,
                body=desk_model.as_text(),
                desk=desk_model,
            )
            await pilot.pause(0.05)
            assert td.query_one("#td-fin-trio").display is True
            assert td.query_one("#td-flow-days").display is False
            assert td.query_one("#td-dist-dual").display is False
            inc = td.query_one("#td-fin-income-body").render().plain
            assert "Revenue" in inc or "28" in inc
            bal = td.query_one("#td-fin-balance-body").render().plain
            assert "Assets" in bal or "1.60" in bal or "T" in bal
            cf = td.query_one("#td-fin-cashflow-body").render().plain
            assert "Op CF" in cf or "47" in cf

    asyncio.run(scenario())
