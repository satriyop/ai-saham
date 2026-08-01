"""Ticker detail = OpenCode panel stack with full facts — not CLI dump, not stubs."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Static

from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_dashboard
from src.adapters.tui.widgets.ticker_desk import TickerDesk, _paint_depth_fact_line


def _rich_dashboard() -> SimpleNamespace:
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
            top_holder_name="DWIMURIA INVESTAMA ANDALAN",
            top_holder_pct=Decimal("54.9"),
            institution_pct=Decimal("31.9"),
            individual_pct=Decimal("6.9"),
            total_shares_formatted="123.28B",
            report_date="2026-03-31",
        ),
        sector_macro_context_evidence=None,
        corp_actions=(
            SimpleNamespace(event_type="dividend", ex_date="2026-06-17", detail="Rp 20"),
            SimpleNamespace(event_type="dividend", ex_date="2026-03-30", detail="Rp 281"),
        ),
        insider_txns=(
            SimpleNamespace(
                transaction_date="2026-03-25",
                name="A. Widodo",
                role="DIR",
                action_type="BUY",
                shares=240569,
                price=6982,
            ),
        ),
        seasonality=None,
        iev_rows=(
            SimpleNamespace(date=date(2026, 7, 31), iep=6425, iev=24900, ncp="✓"),
            SimpleNamespace(date=date(2026, 7, 30), iep=6325, iev=21729, ncp="—"),
        ),
        sentiment_logs=(),
        profile=SimpleNamespace(
            website="www.bca.co.id",
            description="PT Bank Central Asia Tbk commercial banking.",
            ipo_date="2000-05-31",
            ipo_price=1400,
        ),
        candles=(
            SimpleNamespace(
                date=date(2026, 7, 31),
                open=6425,
                high=6450,
                low=6325,
                close=6325,
                volume=153_200_000,
            ),
            SimpleNamespace(
                date=date(2026, 7, 30),
                open=6325,
                high=6450,
                low=6250,
                close=6450,
                volume=152_700_000,
            ),
        ),
        panel_keys=(),
        fetch_hint="saham fetch market BBCA",
        mode="full",
        related_actions=(),
        today=date(2026, 7, 31),
    )


def test_depth_fact_line_is_cockpit_not_raw_dump():
    line = _paint_depth_fact_line("Target  Rp8,228 avg (+30.1%)")
    assert "Target" in line
    assert "#555555" in line  # dim label
    assert "8,228" in line


def test_detail_model_has_full_fact_rows_not_stub_only():
    model = build_ticker_desk_model_from_dashboard(_rich_dashboard())
    by = {p.key: p for p in model.detail_panels}
    assert by["analyst"].status == "present"
    assert any("Target" in ln for ln in by["analyst"].lines)
    assert any("DWIMURIA" in ln for ln in by["ownership"].lines)
    assert any("Individual" in ln for ln in by["ownership"].lines)
    assert len(by["corp_actions"].lines) >= 2
    assert any("BUY" in ln for ln in by["insider"].lines)
    assert any("6425" in ln or "6,425" in ln for ln in by["iev"].lines)
    assert any("www.bca.co.id" in ln for ln in by["profile"].lines)
    # Candles: real OHLC rows, not only a bar count stub
    assert any("Open" in ln or "6,425" in ln or "6425" in ln for ln in by["candles"].lines)
    assert sum(1 for ln in by["candles"].lines if ln[:4].isdigit() or "-" in ln[:10]) >= 1


def test_detail_paint_uses_card_stack_not_cli_box_dump():
    # Deliberately put box-drawing dump in body — paint must ignore it
    fake_cli_dump = "╭──── Analyst ────╮\n│ dump only │\n╰────────────────╯"
    model = build_ticker_desk_model_from_dashboard(_rich_dashboard(), body=fake_cli_dump)

    async def scenario() -> None:
        class _A(App):
            def compose(self) -> ComposeResult:
                yield TickerDesk(id="ticker-desk")

        app = _A()
        async with app.run_test(size=(120, 60)) as pilot:
            await pilot.pause(0.05)
            td = app.query_one("#ticker-desk", TickerDesk)
            td.paint(model, detail_open=True)
            await pilot.pause(0.08)
            more = app.query_one("#td-more-sec")
            assert more.display is True
            # Cockpit: no density-restating section head above stack
            head = app.query_one("#td-more-head", Static)
            assert head.display is False
            # Structured cli-panel cards visible
            analyst = app.query_one("#td-depth-analyst")
            assert analyst.display is True
            assert "td-depth-panel" in analyst.classes
            title = app.query_one("#td-depth-t-analyst", Static).render()
            title_plain = title.plain if hasattr(title, "plain") else str(title)
            assert "ANALYST" in title_plain.upper()
            body = app.query_one("#td-depth-b-analyst", Static).render()
            body_plain = body.plain if hasattr(body, "plain") else str(body)
            assert "Target" in body_plain or "BUY" in body_plain
            # Must NOT paint CLI box dump as the detail surface
            dump_el = app.query_one("#td-more-body", Static)
            dump_plain = (
                dump_el.render().plain
                if hasattr(dump_el.render(), "plain")
                else str(dump_el.render())
            )
            assert "╭" not in dump_plain
            assert "dump only" not in dump_plain
            assert dump_el.display is False
            # Secondary presence stubs never painted (design reject)
            sec = app.query_one("#td-secondary-sec")
            assert sec.display is False
            # Footer keeps fixed word "detail" (chip is-on teaches state)
            foot = app.query_one("#td-footer", Static).render()
            foot_plain = foot.plain if hasattr(foot, "plain") else str(foot)
            assert "d detail" in foot_plain
            assert "d brief" not in foot_plain
            # Candles card has OHLC facts
            cbody = app.query_one("#td-depth-b-candles", Static).render()
            cplain = cbody.plain if hasattr(cbody, "plain") else str(cbody)
            assert "6325" in cplain or "6,325" in cplain or "Open" in cplain
            # Brief closes the stack
            td.paint(model, detail_open=False)
            await pilot.pause(0.05)
            assert app.query_one("#td-more-sec").display is False

    asyncio.run(scenario())
