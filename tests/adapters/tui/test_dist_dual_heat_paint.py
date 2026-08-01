"""Dist job desk · true dual-column heat (design cockpit)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from textual.app import App, ComposeResult

from src.adapters.shared.ticker_dist_desk_model import build_ticker_dist_desk_model
from src.adapters.shared.ticker_flow_desk_model import build_ticker_flow_desk_model
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def _snap() -> SimpleNamespace:
    return SimpleNamespace(
        date=date(2026, 7, 31),
        foreign_buying_from_domestic=True,
        net_foreign_buyer_dominance=False,
        top_buyers=(
            SimpleNamespace(
                broker_code="RX",
                broker_type="Asing",
                amount_idr=12_900_000_000,
                counterparties=(
                    SimpleNamespace(
                        broker_code="CC",
                        broker_type="Pemerintah",
                        amount_idr=1_800_000_000,
                    ),
                    SimpleNamespace(
                        broker_code="XL",
                        broker_type="Lokal",
                        amount_idr=1_500_000_000,
                    ),
                ),
            ),
        ),
        top_sellers=(
            SimpleNamespace(
                broker_code="ZP",
                broker_type="Asing",
                amount_idr=8_000_000_000,
                counterparties=(
                    SimpleNamespace(
                        broker_code="AK",
                        broker_type="Asing",
                        amount_idr=1_800_000_000,
                    ),
                ),
            ),
        ),
    )


def test_dist_dual_heat_columns_mounted_and_painted():
    async def scenario() -> None:
        class _A(App):
            def compose(self) -> ComposeResult:
                yield TickerDesk(id="ticker-desk")

        app = _A()
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause(0.05)
            desk = app.query_one("#ticker-desk", TickerDesk)
            model = build_ticker_desk_model_from_text(ticker="UNVR", body="Close: 1755")
            desk.paint(model, detail_open=False)
            dist = build_ticker_dist_desk_model(
                "UNVR",
                _snap(),
                as_of=date(2026, 7, 31),
                source="broker_distribution_cache",
            )
            desk.set_job_view("dist", title=dist.title, body=dist.as_text(), desk=dist)
            await pilot.pause(0.05)

            dual = desk.query_one("#td-dist-dual")
            assert dual.display is True
            # Sessions dump hidden when dual heat is on
            assert desk.query_one("#td-flow-days").display is False

            buy_body = str(desk.query_one("#td-dist-buy-body").render().plain)
            sell_body = str(desk.query_one("#td-dist-sell-body").render().plain)
            assert "RX" in buy_body
            assert "ZP" in sell_body
            # F/L pills, never Asing letter A as type tag
            assert "(F)" in buy_body or "F" in buy_body
            assert "[A]" not in buy_body
            # Horizontal track markers present (hollow bar residual ░ or filled █)
            assert "█" in buy_body or "░" in buy_body
            # Arrow directions
            assert "←" in buy_body
            assert "→" in sell_body

            # Flow job hides dual
            flow = build_ticker_flow_desk_model(
                "UNVR",
                (
                    SimpleNamespace(
                        date=date(2026, 7, 30),
                        foreign_net_value=Decimal("1e9"),
                        foreign_flow_ratio=Decimal("5"),
                        is_foreign_accumulating=True,
                        top_buyers=(),
                        top_sellers=(),
                        source="idx",
                    ),
                ),
                window_days=10,
            )
            desk.set_job_view("flow", title=flow.title, body=flow.as_text(), desk=flow)
            await pilot.pause(0.05)
            assert desk.query_one("#td-dist-dual").display is False
            assert desk.query_one("#td-flow-days").display is True

    asyncio.run(scenario())
