"""Quiet in-place load: chip is-on, hold show, no plain-text Loading dump."""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def test_pending_job_holds_show_no_loading_essay():
    async def scenario() -> None:
        class _A(App):
            def compose(self) -> ComposeResult:
                yield TickerDesk(id="ticker-desk")

        app = _A()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            td = app.query_one("#ticker-desk", TickerDesk)
            model = build_ticker_desk_model_from_text(
                ticker="BBCA",
                body="LAST · LOCAL CLOSE\n1000\nlocal cache",
            )
            td.paint(model, detail_open=False)
            # Pending open: chip on, empty payload
            td.set_job_view("flow", title="View · ticker · BBCA · flow", body="", desk=None)
            await pilot.pause(0.05)
            assert td._active_job == "flow"
            assert not (td._job_body or "").strip()
            assert td._job_desk is None
            # Show mast still visible (hold body until ready)
            assert td.query_one("#td-mast").display is True
            assert td.query_one("#td-job-sec").display is False
            crumb = td.query_one("#td-crumb").render().plain
            assert "flow" in crumb
            assert "loading" in crumb.lower()
            body_plain = td.query_one("#td-job-body").render().plain
            assert "Loading flow" not in body_plain
            assert "saham view ticker" not in body_plain

    asyncio.run(scenario())
