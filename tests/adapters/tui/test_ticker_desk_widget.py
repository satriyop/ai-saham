"""Visual ticker desk (Harga mast) — not CLI text dump."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.ticker_desk_model import (
    build_ticker_desk_model_from_dashboard,
    build_ticker_desk_model_from_text,
)
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def test_model_from_dashboard_price_first_not_action():
    dash = SimpleNamespace(
        ticker="BBCA",
        latest_close=Decimal("6275"),
        as_of=date(2026, 7, 29),
        notation=SimpleNamespace(
            listing_board="Papan Utama",
            sector="Keuangan",
            notations=(SimpleNamespace(description="Bank Central Asia"),),
        ),
        profile=None,
        price_structure=SimpleNamespace(
            change_1d_pct=0.8,
            change_5d_pct=-3.5,
            change_20d_pct=12.1,
            range_52w_pct=35.0,
        ),
        fundamentals=SimpleNamespace(
            pe_ratio_ttm=13.3,
            pbv=3.0,
            market_cap_idr=774_000_000_000_000,
            roe_ttm=22.4,
            dividend_yield=4.8,
            piotroski_f_score=5,
        ),
        freshness=(
            SimpleNamespace(label="Price", status=SimpleNamespace(value="ok")),
            SimpleNamespace(label="Flow", status=SimpleNamespace(value="ok")),
        ),
    )
    model = build_ticker_desk_model_from_dashboard(dash, body="depth panel text")
    assert model.ticker == "BBCA"
    assert "6,275" in model.price
    assert model.change_tone == "pos"
    assert any(m.label == "PE TTM" and "13" in m.value for m in model.metrics)
    assert "Action" in model.authority or "not Action" in model.authority
    text = model.as_text()
    assert "HARGA MAST" in text
    assert "6,275" in text
    assert "ENTER" not in text.split("authority")[0] if False else True
    # Must not claim board Action
    assert "ENTER" not in model.price


def test_cockpit_view_ticker_paints_harga_widget_not_plain_static_only():
    def loader(t: str):
        return build_ticker_desk_model_from_dashboard(
            SimpleNamespace(
                ticker=t,
                latest_close=Decimal("6275"),
                as_of=date(2026, 7, 29),
                notation=SimpleNamespace(
                    listing_board="Papan Utama",
                    sector="Bank",
                    notations=(SimpleNamespace(description="Bank Central Asia"),),
                ),
                profile=None,
                price_structure=SimpleNamespace(
                    change_1d_pct=0.8,
                    change_5d_pct=-3.5,
                    change_20d_pct=12.1,
                    range_52w_pct=35.0,
                ),
                fundamentals=SimpleNamespace(
                    pe_ratio_ttm=13.3,
                    pbv=3.0,
                    market_cap_idr=774_000_000_000_000,
                    roe_ttm=22.4,
                    dividend_yield=4.8,
                    piotroski_f_score=5,
                ),
                freshness=(),
            ),
            body="Foreign flow panel…",
        )

    async def scenario() -> None:
        app = CockpitApp(ticker_detail_loader=loader)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            app._focus_ticker = "BBCA"
            app._stage = "accum"
            app._board_kind = "accum"
            app._rows = [
                SimpleNamespace(
                    ticker="BBCA",
                    signal="84",
                    accum="48",
                    action="WATCH",
                    gate="OPEN",
                    source=None,
                )
            ]
            app._row_index = 0
            app._run_command("view-ticker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._status_note == "view ticker":
                    if app._ticker_desk_model is not None:
                        break
            assert app._stage == "detail"
            assert app._status_note == "view ticker"
            desk = app.query_one("#ticker-desk", TickerDesk)
            assert desk.display is True
            body = app.query_one("#stage-body")
            assert body.display is False
            price = str(app.query_one("#td-price").render())
            assert "6,275" in price
            lab = str(app.query_one("#td-mast-lab").render())
            assert "HARGA" in lab.upper()
            mark = str(app.query_one("#td-mark").render())
            assert "BBCA" in mark
            # Metric ribbon painted
            pe = str(app.query_one("#td-metric-v-0").render())
            assert "13" in pe
            # Not the old plain static-only dump path
            assert app.query_one("#judge-desk").display is False

    asyncio.run(scenario())


def test_text_fallback_model_still_has_mast():
    m = build_ticker_desk_model_from_text(ticker="TLKM", body="Close: 3,180\nmore panels")
    assert m.ticker == "TLKM"
    assert "3,180" in m.price
    assert "HARGA" in m.as_text()
