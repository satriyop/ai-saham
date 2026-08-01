"""Brokers chip stays on ticker job shell — not independent ticker-desks stage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.shared.view_ticker_job_text import format_ticker_brokers_job
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text


def _fake_dashboard(ticker: str) -> object:
    return build_ticker_desk_model_from_text(
        ticker=ticker,
        body=f"View · ticker desk · {ticker}\nLAST · LOCAL CLOSE\nRp 1,755\n",
    )


def _job_loader(job: str, ticker: str):
    if job == "brokers":
        rows = (
            SimpleNamespace(
                code="YP",
                type_label="Foreign",
                role="buy",
                as_of="2026-07-31",
                day_net="+1.2B",
                net3="+0.8B",
                net5="+3.0B",
                net7="+3.5B",
                net10="+4.0B",
                net20="+5.0B",
                streak="2",
                delta1="+0.1B",
                has_partial_netx=False,
            ),
            SimpleNamespace(
                code="CC",
                type_label="Local",
                role="sell",
                as_of="2026-07-31",
                day_net="-0.5B",
                net3="-0.2B",
                net5="-1.0B",
                net7="-1.1B",
                net10="-1.2B",
                net20="-1.5B",
                streak="0",
                delta1="-0.2B",
                has_partial_netx=False,
            ),
        )
        return format_ticker_brokers_job(ticker, rows, as_of="2026-07-31")
    from src.adapters.shared.view_ticker_job_text import empty_ticker_job

    return empty_ticker_job(job, ticker, message="stub")


def test_brokers_chip_stays_on_ticker_detail_stage():
    async def scenario() -> None:
        app = CockpitApp(
            ticker_detail_loader=_fake_dashboard,
            ticker_job_loader=_job_loader,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            app._stage = "detail"
            app._status_note = "view ticker"
            app._focus_ticker = "UNVR"
            app._ticker_desk_model = _fake_dashboard("UNVR")
            app._refresh_chrome()
            await pilot.pause(0.05)

            app.action_ticker_job("brokers")
            # Worker path: inject ready payload directly if worker slow
            await pilot.pause(0.3)
            # Force ready if still loading
            if app._ticker_job != "brokers":
                payload = _job_loader("brokers", "UNVR")
                app._on_ticker_job_ready("brokers", "UNVR", payload)
                await pilot.pause(0.05)

            assert app._stage == "detail"
            assert app._ticker_job == "brokers"
            assert app._status_note == "view ticker brokers"
            assert app._stage != "ticker-desks"
            assert len(app._broker_rows) == 2

            # Switch to flow-like close via second press
            app.action_ticker_job("brokers")
            await pilot.pause(0.05)
            assert app._ticker_job is None
            assert app._status_note == "view ticker"
            assert app._stage == "detail"

    asyncio.run(scenario())
