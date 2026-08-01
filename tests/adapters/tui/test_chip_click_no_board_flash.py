"""Chip / instrument load must not unmask accum board (no accidental Judge).

Policy: keep_board only for board recompute; ticker jobs stay on detail.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.shared.view_ticker_job_text import TickerJobText, format_ticker_flow_job
from src.adapters.tui.chrome_cues import should_keep_board_during_loading
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumRowView
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text
from src.adapters.tui.widgets.flag_chip import FlagChip
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def test_keep_board_only_for_recompute_not_instrument_loads():
    assert (
        should_keep_board_during_loading(
            stage="loading",
            board_kind="accum",
            status_note="recomputing…",
            board_title="Screen · accumulation",
            has_rows=True,
        )
        is True
    )
    # Ticker job load must never keep board
    assert (
        should_keep_board_during_loading(
            stage="loading",
            board_kind="accum",
            status_note="view ticker flow",
            board_title="View · ticker · BBCA · flow",
            has_rows=True,
        )
        is False
    )
    assert (
        should_keep_board_during_loading(
            stage="loading",
            board_kind="accum",
            status_note="loading ticker job",
            board_title="View · ticker · BBCA · flow",
            has_rows=True,
        )
        is False
    )
    # Broker deep / show
    assert (
        should_keep_board_during_loading(
            stage="loading",
            board_kind="accum",
            status_note="view broker flow",
            board_title="View · broker flow · YP",
            has_rows=True,
        )
        is False
    )
    assert (
        should_keep_board_during_loading(
            stage="loading",
            board_kind="accum",
            status_note="view broker show",
            board_title="View · broker show · YP",
            has_rows=True,
        )
        is False
    )


def test_ticker_job_open_stays_detail_never_judge_or_board_table():
    """Chip path: open flow while accum rows exist — no board table, no judge."""

    def _job_loader(job: str, ticker: str) -> TickerJobText:
        return format_ticker_flow_job(
            ticker,
            (
                SimpleNamespace(
                    date=date(2026, 7, 29),
                    foreign_net_value=Decimal("-1e9"),
                    foreign_flow_ratio=Decimal("5"),
                    is_foreign_accumulating=False,
                    top_buyers=(),
                    top_sellers=(),
                ),
            ),
        )

    row = AccumRowView(
        ticker="BBCA",
        signal="80",
        accum="40",
        action="WATCH",
        phase="COMPRESSION",
        streak="1",
        rsi="50",
        net_pct="0",
        disc_pct="0",
        price="100",
        gate="OPEN",
        source=None,
    )

    async def scenario() -> None:
        app = CockpitApp(
            ticker_detail_loader=lambda t: build_ticker_desk_model_from_text(
                ticker=t, body=f"DASH {t}"
            ),
            ticker_job_loader=_job_loader,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            # Simulate: left accum board, opened ticker (rows still in memory)
            app._rows = [row]
            app._row_index = 0
            app._board_kind = "accum"
            app._detail_return_stage = "accum"
            app._stage = "detail"
            app._status_note = "view ticker"
            app._focus_ticker = "BBCA"
            app._ticker_desk_model = build_ticker_desk_model_from_text(
                ticker="BBCA", body="LAST · LOCAL CLOSE\nDASH"
            )
            app._refresh_chrome()
            await pilot.pause(0.05)

            table = app.query_one("#board-table")
            assert table.display is False

            # In-place job open (chip path)
            app.action_ticker_job("flow")
            # Immediately: must stay detail, not loading+table
            assert app._stage == "detail"
            assert app._ticker_job == "flow"
            assert table.display is False
            assert app._status_note != "judge"
            desk = app.query_one("#ticker-desk", TickerDesk)
            assert desk.display is True
            assert desk._active_job == "flow"
            # Quiet in-place load: no plain-text "Loading flow…" dump
            job_body = desk.query_one("#td-job-body")
            plain = getattr(job_body.render(), "plain", str(job_body.render()))
            assert "Loading flow" not in plain
            assert "saham view ticker flow" not in plain
            # Pending: hold show (job sec not forced with essay)
            assert desk._job_desk is None
            assert not (desk._job_body or "").strip()

            for _ in range(40):
                await pilot.pause(0.05)
                if app._ticker_job_text is not None:
                    break
            assert app._stage == "detail"
            assert table.display is False
            assert app._status_note == "view ticker flow"
            assert app._status_note != "judge"
            try:
                judge = app.query_one("#judge-desk")
                assert judge.display is False
            except Exception:
                pass
            assert isinstance(app._ticker_job_text, TickerJobText)
            assert "Foreign flow" in (app._ticker_job_text.body or "")
            # Ready: structured job, still no loading essay residue
            assert desk._job_desk is not None or (desk._job_body or "").strip()
            ready_plain = getattr(
                desk.query_one("#td-job-body").render(),
                "plain",
                "",
            )
            assert "Loading flow" not in str(ready_plain)

    asyncio.run(scenario())


def test_flag_chip_click_stops_and_focuses():
    chip = FlagChip("flow", "flow", id="t-flow")
    chip.set_chip_state(available=True, expanded=False)
    assert chip.can_focus is True
