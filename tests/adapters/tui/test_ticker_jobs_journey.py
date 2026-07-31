"""Ticker job chips — real loader path + esc trail (not stub bodies)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.shared.view_ticker_job_text import (
    TickerJobText,
    format_ticker_flow_job,
)
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def _fake_dashboard(ticker: str) -> object:
    body = f"View · ticker desk · {ticker}\nLAST · LOCAL CLOSE\nRp 6,275\nDASHBOARD_FOR_{ticker}\n"
    return build_ticker_desk_model_from_text(ticker=ticker, body=body)


def _job_loader(job: str, ticker: str) -> TickerJobText:
    """Deterministic loader using real formatters (same shape as composition)."""
    ticker_u = str(ticker).upper()
    if job == "flow":
        summaries = (
            SimpleNamespace(
                date=date(2026, 7, 29),
                foreign_net_value=Decimal("-27800000000"),
                foreign_flow_ratio=Decimal("5.0"),
                is_foreign_accumulating=False,
                top_buyers=(SimpleNamespace(broker_code="YP"),),
                top_sellers=(SimpleNamespace(broker_code="AK"),),
            ),
        )
        return format_ticker_flow_job(ticker_u, summaries)
    from src.adapters.shared.view_ticker_job_text import (
        format_ticker_distribution_job,
        format_ticker_financials_job,
        format_ticker_foreign_history_job,
    )

    if job == "foreign":
        return format_ticker_foreign_history_job(
            ticker_u,
            (
                SimpleNamespace(
                    date=date(2026, 7, 29),
                    source="stockbit",
                    net_val=Decimal("-1e9"),
                    net_lot=-10,
                    avg_price=Decimal("1000"),
                ),
            ),
            resolved_source="stockbit",
        )
    if job == "dist":
        return format_ticker_distribution_job(
            ticker_u,
            SimpleNamespace(
                date=date(2026, 7, 29),
                foreign_buying_from_domestic=False,
                net_foreign_buyer_dominance=False,
                top_buyers=(
                    SimpleNamespace(
                        broker_code="YP",
                        broker_type="asing",
                        amount_idr=1_000_000_000,
                        counterparties=(),
                    ),
                ),
                top_sellers=(),
            ),
        )
    if job == "fin":
        p = SimpleNamespace(
            period_end=date(2026, 3, 31),
            total_revenue=1e12,
            net_income=1e11,
            eps_basic=10.0,
            total_assets=None,
            stockholders_equity=None,
            total_debt=None,
            operating_cash_flow=None,
            free_cash_flow=None,
            capital_expenditure=None,
            source="yahoo",
        )
        return format_ticker_financials_job(
            ticker_u,
            (
                SimpleNamespace(
                    statement="income",
                    period_type="quarter",
                    status="ok",
                    periods=(p,),
                    source="yahoo",
                    message=None,
                    fetch_hint=f"saham fetch financials {ticker_u}",
                ),
            ),
        )
    raise AssertionError(f"unexpected job {job}")


def test_ticker_jobs_open_real_bodies_and_esc_to_show():
    async def scenario() -> None:
        app = CockpitApp(
            # No accum_loader — avoid on_mount board load racing job workers
            ticker_detail_loader=_fake_dashboard,
            ticker_job_loader=_job_loader,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            app._stage = "detail"
            app._status_note = "view ticker"
            app._focus_ticker = "BBCA"
            app._ticker_desk_model = _fake_dashboard("BBCA")
            app._ticker_detail_open = False
            app._detail_return_stage = "shell"
            app._refresh_chrome()
            await pilot.pause(0.1)

            for job, key_hint in (
                ("flow", "flow"),
                ("foreign", "history"),
                ("dist", "TOP BUYERS"),
                ("fin", "Income"),
            ):
                # Ensure show gate between jobs
                if app._ticker_job is not None and app._ticker_job != job:
                    app._close_ticker_job()
                    await pilot.pause(0.05)
                app._status_note = "view ticker"
                app._stage = "detail"
                app.action_ticker_job(job)
                for _ in range(40):
                    await pilot.pause(0.05)
                    if app._ticker_job == job and app._ticker_job_text is not None:
                        break
                assert app._ticker_job == job
                body = (app._detail_text or "").lower()
                assert "ships later" not in body
                assert "full table paint ships" not in body
                jt = app._ticker_job_text
                assert isinstance(jt, TickerJobText)
                assert jt.job == job
                assert key_hint.lower() in jt.body.lower() or key_hint in jt.body
                desk = app.query_one("#ticker-desk", TickerDesk)
                assert desk._active_job == job
                assert desk.query_one("#td-job-sec").display is True

            # esc from job → show
            density_before = app._ticker_detail_open
            app.action_go_back()
            await pilot.pause(0.1)
            assert app._ticker_job is None
            assert app._status_note == "view ticker"
            assert app._ticker_detail_open is density_before
            desk = app.query_one("#ticker-desk", TickerDesk)
            assert desk._active_job is None

            # second press same job toggles closed after open
            app.action_ticker_job("flow")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._ticker_job == "flow":
                    break
            assert app._ticker_job == "flow"
            app.action_ticker_job("flow")
            await pilot.pause(0.1)
            assert app._ticker_job is None

    asyncio.run(scenario())


def test_ticker_job_loader_composition_uses_use_case_path():
    """Composition loader class is wired; smoke import path."""
    from src.adapters.tui.composition import _TickerJobLoader

    assert callable(_TickerJobLoader)
    # empty path with temp db may be empty — call format via empty
    from src.adapters.shared.view_ticker_job_text import empty_ticker_job

    e = empty_ticker_job("flow", "ZZZZ")
    assert e.empty is True
    assert "view ticker flow" in e.cli_verb
