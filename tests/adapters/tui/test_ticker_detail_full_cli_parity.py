"""Ticker detail density must surface full CLI show text — not thin inventory lines."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Static

from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_dashboard
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def _rich_dashboard() -> SimpleNamespace:
    """Minimal full-mode dashboard with multi-line CLI-style body attached via builder."""
    return SimpleNamespace(
        ticker="BBCA",
        latest_close=Decimal("6325"),
        as_of=date(2026, 7, 31),
        notation=SimpleNamespace(
            name="Bank Central Asia",
            board="Utama",
            sector="Keuangan",
            is_tradeable=True,
        ),
        price_structure=SimpleNamespace(
            change_1d_pct=Decimal("-1.9"),
            change_5d_pct=Decimal("0.8"),
            change_20d_pct=Decimal("4.5"),
            high_52w=Decimal("8975"),
            low_52w=Decimal("4820"),
            volume=153_200_000,
            avg_volume_20d=167_900_000,
        ),
        fundamentals=SimpleNamespace(
            pe_ratio_ttm=Decimal("13.3"),
            pb_ratio=Decimal("3.0"),
            market_cap=Decimal("773550000000000"),
            roe=Decimal("0.224"),
        ),
        freshness=(),
        foreign_flow_points=(),
        foreign_flow_source="stockbit",
        bandar=None,
        earnings=(),
        analyst=SimpleNamespace(
            buy_count=35,
            hold_count=2,
            sell_count=0,
            consensus_label="BUY",
            avg_price_target=Decimal("8228"),
            upside_pct=Decimal("30.1"),
            price_target_low=Decimal("6000"),
            price_target_high=Decimal("10900"),
            last_updated="2026-07-27",
            fetched_at=date(2026, 7, 31),
        ),
        ownership=SimpleNamespace(
            top_holder_name="DWIMURIA",
            top_holder_pct=Decimal("54.9"),
            institution_pct=Decimal("31.9"),
            individual_pct=None,
            total_shares_formatted="—",
            report_date=None,
        ),
        sector_macro_context_evidence=None,
        corp_actions=(),
        insider_txns=(),
        seasonality=None,
        iev_rows=(),
        sentiment_logs=(),
        profile=SimpleNamespace(website="www.bca.co.id", description="Bank umum"),
        candles=(
            SimpleNamespace(
                date=date(2026, 7, 31),
                open=6425,
                high=6450,
                low=6325,
                close=6325,
                volume=153_200_000,
            ),
        ),
        panel_keys=(),
        fetch_hint="saham fetch market BBCA",
        mode="full",
        related_actions=(),
        today=date(2026, 7, 31),
    )


def test_detail_paint_surfaces_full_cli_body_not_thin_inventory():
    full_cli = """
╭───────────────────────────── Analyst Consensus ──────────────────────────────╮
│   35B · 2H · 0S  →  BUY                                                      │
│   Target  Rp8,228 avg  (+30.1%)                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─────────────────────────────── Recent Candles ───────────────────────────────╮
│ Date         Open  High   Low Close  Volume                                  │
│ 2026-07-31  6,425 6,450 6,325 6,325 153.2 M                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
  Run `saham fetch market BBCA` to refresh stale or missing data.
""".strip()

    model = build_ticker_desk_model_from_dashboard(_rich_dashboard(), body=full_cli)
    assert "Analyst Consensus" in model.body
    assert "Recent Candles" in model.body
    assert "6,425" in model.body

    async def scenario() -> None:
        class _A(App):
            def compose(self) -> ComposeResult:
                yield TickerDesk(id="ticker-desk")

        app = _A()
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause(0.05)
            td = app.query_one("#ticker-desk", TickerDesk)
            # Brief: full dump hidden
            td.paint(model, detail_open=False)
            await pilot.pause(0.05)
            more = app.query_one("#td-more-sec")
            assert more.display is False

            # Detail: full CLI body must appear (not present/missing stubs only)
            td.paint(model, detail_open=True)
            await pilot.pause(0.05)
            assert more.display is True
            body = app.query_one("#td-more-body", Static)
            assert body.display is True
            plain = body.render().plain if hasattr(body.render(), "plain") else str(body.render())
            assert "Analyst Consensus" in plain
            assert "Recent Candles" in plain
            assert "6,425" in plain
            assert "full show" in app.query_one("#td-more-head", Static).render().plain.lower() or (
                "CLI" in app.query_one("#td-more-head", Static).render().plain
            )
            # Must not be the old thin inventory-only surface
            assert "present/missing" not in plain.lower()

    asyncio.run(scenario())
