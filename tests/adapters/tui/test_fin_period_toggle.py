"""Fin period grain · binary toggle y · quarterly ↔ annual (design lock)."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from textual.app import App, ComposeResult

from src.adapters.shared.ticker_fin_desk_model import build_ticker_fin_desk_model
from src.adapters.shared.view_ticker_job_text import TickerJobText, format_ticker_financials_job
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_text
from src.adapters.tui.widgets.flag_chip import FlagChip
from src.adapters.tui.widgets.ticker_desk import TickerDesk


def _fin_results(*, period_type: str = "quarter") -> tuple[SimpleNamespace, ...]:
    pe = date(2025, 12, 31) if period_type == "annual" else date(2026, 3, 31)
    return (
        SimpleNamespace(
            statement="income",
            period_type=period_type,
            status="ok",
            source="yahoo",
            periods=(
                SimpleNamespace(
                    period_end=pe,
                    total_revenue=28e12 if period_type == "quarter" else 110e12,
                    net_income=14e12 if period_type == "quarter" else 56e12,
                    eps_basic=119.0 if period_type == "quarter" else 456.0,
                    total_assets=None,
                    stockholders_equity=None,
                    total_debt=None,
                    operating_cash_flow=None,
                    free_cash_flow=None,
                    capital_expenditure=None,
                ),
            ),
            message=None,
            fetch_hint="saham fetch financials BBCA",
        ),
        SimpleNamespace(
            statement="balance",
            period_type=period_type,
            status="ok",
            source="yahoo",
            periods=(
                SimpleNamespace(
                    period_end=pe,
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
            fetch_hint="saham fetch financials BBCA",
        ),
        SimpleNamespace(
            statement="cashflow",
            period_type=period_type,
            status="empty",
            source="yahoo",
            periods=(),
            message="No cashflow periods cached",
            fetch_hint="saham fetch financials BBCA",
        ),
    )


def test_fin_period_chip_flip_label_and_is_on_annual():
    async def scenario() -> None:
        class _A(App):
            def compose(self) -> ComposeResult:
                yield TickerDesk(id="ticker-desk")

            def __init__(self) -> None:
                super().__init__()
                self._ticker_fin_period = "quarterly"

        app = _A()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            td = app.query_one("#ticker-desk", TickerDesk)
            model = build_ticker_desk_model_from_text(ticker="BBCA", body="Close: 1")
            td.paint(model, detail_open=False)
            period = app.query_one("#td-flag-period", FlagChip)
            # Off fin: fin sub-chip hidden (not dim-on-bar)
            assert period.power_key == "y"
            assert period.display is False
            assert "is-context-off" in period.classes
            assert period.size.width == 0

            desk_q = build_ticker_fin_desk_model("BBCA", _fin_results(period_type="quarter"))
            td.set_job_view("fin", title=desk_q.title, body=desk_q.as_text(), desk=desk_q)
            await pilot.pause(0.05)
            assert period.display is True
            assert "is-context-off" not in period.classes
            assert period.word == "quarterly"
            assert "is-on" not in period.classes
            assert period.size.width > 0

            app._ticker_fin_period = "annual"
            desk_a = build_ticker_fin_desk_model("BBCA", _fin_results(period_type="annual"))
            td.set_job_view("fin", title=desk_a.title, body=desk_a.as_text(), desk=desk_a)
            await pilot.pause(0.05)
            assert period.display is True
            assert period.word == "annual"
            assert "is-on" in period.classes
            assert desk_a.hero_big == "FY 2025"

            # Other job → [y] removed from bar (not dim)
            td.set_job_view("flow", title="flow", body="flow body")
            await pilot.pause(0.05)
            assert period.display is False
            assert "is-context-off" in period.classes
            assert period.size.width == 0

            # Leave fin → still hidden
            td.set_job_view(None)
            await pilot.pause(0.05)
            assert period.display is False
            assert "is-context-off" in period.classes

    asyncio.run(scenario())


def test_toggle_fin_period_action_reloads_with_grain():
    calls: list[tuple[str, str, str]] = []

    def _loader(job: str, ticker: str, fin_period: str = "quarterly") -> TickerJobText:
        calls.append((job, ticker, fin_period))
        grain = "annual" if fin_period == "annual" else "quarter"
        results = _fin_results(period_type=grain)
        return format_ticker_financials_job(ticker, results, fetch_hint=results[0].fetch_hint)

    async def scenario() -> None:
        app = CockpitApp(
            ticker_detail_loader=lambda t: (f"View · ticker · {t}\nClose: 1\nlocal cache",)[0],
            ticker_job_loader=_loader,
        )
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            app._stage = "detail"
            app._status_note = "view ticker"
            app._focus_ticker = "BBCA"
            app._ticker_desks_stock = "BBCA"
            app._ticker_job = "fin"
            app._ticker_fin_period = "quarterly"
            # Seed desk so stage is instrument ticker
            app._board_title = "View · ticker · BBCA · fin"
            app.action_toggle_fin_period()
            await pilot.pause(0.3)
            assert app._ticker_fin_period == "annual"
            assert any(c[2] == "annual" for c in calls)
            app.action_toggle_fin_period()
            await pilot.pause(0.3)
            assert app._ticker_fin_period == "quarterly"

    asyncio.run(scenario())


def test_y_noop_when_not_on_fin():
    calls: list[tuple[str, str, str]] = []

    def _loader(job: str, ticker: str, fin_period: str = "quarterly") -> TickerJobText:
        calls.append((job, ticker, fin_period))
        return format_ticker_financials_job(
            ticker, _fin_results(period_type="quarter"), fetch_hint="hint"
        )

    async def scenario() -> None:
        app = CockpitApp(ticker_job_loader=_loader)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(0.05)
            app._stage = "detail"
            app._status_note = "view ticker"
            app._focus_ticker = "BBCA"
            app._ticker_job = "flow"
            app._ticker_fin_period = "quarterly"
            before = list(calls)
            app.action_toggle_fin_period()
            await pilot.pause(0.1)
            assert app._ticker_fin_period == "quarterly"
            assert calls == before

    asyncio.run(scenario())
