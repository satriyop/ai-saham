"""Golden pilots for locked v1 agent stage UX (offline, no live provider).

Locks: docs/roadmap/tui_ai_agent_implementation_journey.md
§ Agent stage UX locks (v1) — U1–U13 regression surface.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Input, Static

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.agent_commentary import AgentCommentary
from src.application.dto.accumulation_agent import AgentTurnResult, AgentTurnStatus
from tests.adapters.tui.agent_board_fixtures import agent_accum_payload as _accum_payload

pytestmark = pytest.mark.agent


async def _boot_judge(app: CockpitApp, pilot) -> object:
    for _ in range(40):
        await pilot.pause(0.05)
        if app._stage == "accum" and app._rows:
            break
    assert app._rows, "accum board did not load"
    app._open_detail()
    await pilot.pause()
    source = app._rows[app._row_index].source
    assert source is not None
    return source


def test_golden_slash_opens_agent_stage_and_esc_restores_judge() -> None:
    """U1, U4, U5 — / replaces stage; Esc restores Judge."""

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=lambda request: AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="ok",
                context_reference="sha256:test",
                provider="deepseek",
                model="deepseek-v4-flash",
            ),
            agent_provider="deepseek",
            agent_provider_available=True,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await _boot_judge(app, pilot)
            assert app.query_one("#judge-desk").display is True

            app.action_focus_agent()
            await pilot.pause()
            assert app._prompt_mode == "agent"
            assert app._agent_stage_open is True
            assert app.query_one("#judge-desk").display is False
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            assert commentary.display is True
            assert commentary.has_class("is-stage")
            status = str(app.query_one(".agent-status", Static).content)
            assert "Turn" in status

            app.action_go_back()
            await pilot.pause()
            assert app._agent_stage_open is False
            assert commentary.display is False
            # Judge paint restored via chrome refresh
            assert app._stage == "detail"

    asyncio.run(scenario())


def test_golden_free_text_auto_agent_and_status_strip_do_guides() -> None:
    """U2, U6, U7, U8 — free-text auto agent; strip ranks notes with Do guides."""

    async def scenario() -> None:
        seen: list[str] = []

        def runner(request):
            seen.append(request.user_text)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="Deterministic Action remains ENTER.",
                context_reference="sha256:ctx",
                provider="deepseek",
                model="deepseek-v4-flash",
                warnings=(
                    "Risk snapshot 2026-07-31 differs from decision as-of 2026-08-03; "
                    "risk is shown as diagnostic only",
                    "SESSION_ALIGNED_LATE_WITHIN_LAG",
                    "Incomplete signal authority coverage — flow_confirmation: "
                    "present but not source-authoritative",
                    "bandar_detector",
                ),
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider="deepseek",
            agent_provider_available=True,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await _boot_judge(app, pilot)
            assert app._prompt_mode == "idle"

            inp = app.query_one("#prompt-input", Input)
            inp.value = "apakah signal bagus?"
            app.on_input_submitted(Input.Submitted(inp, inp.value))
            for _ in range(30):
                await pilot.pause(0.05)
                if seen:
                    break

            assert app._prompt_mode == "agent"
            assert seen == ["apakah signal bagus?"]
            assert app._agent_stage_open is True
            assert app.query_one("#judge-desk").display is False

            commentary = app.query_one("#agent-commentary", AgentCommentary)
            status = str(commentary.query_one(".agent-status", Static).content)
            answer = str(commentary.query_one(".agent-answer", Static).content)
            assert "Turn  OK" in status
            assert "RISK_SNAPSHOT_LAG" in status or "Risk lag" in status
            assert "AUTHORITY_INCOMPLETE" in status or "Authority" in status
            # Do guides present for primary notes
            assert "Do" in status or "secondary" in status.lower() or "refresh" in status.lower()
            assert "ENTER" in answer
            more = str(commentary.query_one(".agent-more", Static).content)
            # bandar / extra notes collapse under More when primary is full
            assert "More data notes" in more or more == ""

            # Mode chrome must not claim not-wired when provider available (U13)
            sub = str(app.query_one("#prompt-sub", Static).content)
            assert "not wired" not in sub.lower()

    asyncio.run(scenario())


def test_golden_board_list_rejects_agent_without_inventing_context() -> None:
    """U5 — agent requires Judge; board list does not dispatch."""

    async def scenario() -> None:
        seen: list[str] = []

        def runner(request):
            seen.append(request.user_text)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="should not run",
                context_reference="sha256:x",
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
        )
        async with app.run_test(size=(100, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            app._set_prompt_mode_chip("agent")
            app._submit_agent_turn("should not dispatch on board")
            await pilot.pause()
            assert seen == []

    asyncio.run(scenario())


def test_golden_provider_failure_shows_explicit_error() -> None:
    """U12 — failures are visible, not a blank stage."""

    async def scenario() -> None:
        def runner(request):
            return AgentTurnResult(
                status=AgentTurnStatus.FAILED,
                error_message=(
                    "Agent provider returned an invalid response: DeepSeek response text is empty"
                ),
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
        )
        async with app.run_test(size=(100, 36)) as pilot:
            await _boot_judge(app, pilot)
            app._submit_agent_turn("why?")
            for _ in range(30):
                await pilot.pause(0.05)
                if app._agent_loading is False and app._agent_stage_open:
                    err = str(
                        app.query_one("#agent-commentary").query_one(".agent-error", Static).content
                    )
                    if err:
                        break
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            err = str(commentary.query_one(".agent-error", Static).content)
            status = str(commentary.query_one(".agent-status", Static).content)
            assert "invalid response" in err.lower() or "empty" in err.lower()
            assert "FAIL" in status

    asyncio.run(scenario())


def test_golden_accum_board_refuses_without_multi_stage_flag() -> None:
    """U5 — board alone refuses when ai.cockpit_multi_stage is false."""

    async def scenario() -> None:
        seen = []

        def runner(request):
            seen.append(request)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="should not run",
                context_reference="sha256:x",
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
            agent_cockpit_multi_stage=False,
        )
        async with app.run_test(size=(100, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            app._submit_agent_turn("summarize the board")
            await pilot.pause()
            assert seen == []

    asyncio.run(scenario())


def test_golden_accum_board_opens_with_multi_stage_flag() -> None:
    """U5 / ADR-066 — accum_screen destination when flag on."""

    async def scenario() -> None:
        seen = []

        def runner(request):
            seen.append(request.stage_context)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="Board cohort summary only.",
                context_reference=request.stage_context.context_reference,
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
            agent_cockpit_multi_stage=True,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            app.action_focus_agent()
            await pilot.pause()
            assert app._agent_stage_open is True
            app._submit_agent_turn("Summarize top names on this board")
            for _ in range(40):
                await pilot.pause(0.05)
                if seen and not app._agent_loading:
                    break
            assert len(seen) == 1
            ctx = seen[0]
            assert ctx.stage_kind.value == "accum_screen"
            assert ctx.schema_id == "tui_agent.accum_screen.v1"
            assert ctx.shown == min(20, ctx.cohort_total)
            assert ctx.context_reference.startswith("sha256:")
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            for _ in range(20):
                await pilot.pause(0.05)
                answer = str(commentary.query_one(".agent-answer").content)
                if "Board cohort" in answer or "summary" in answer.lower():
                    break
            assert "Board cohort" in answer or "summary" in answer.lower()

    asyncio.run(scenario())


def test_golden_view_ticker_refuses_without_multi_stage_flag() -> None:
    """U5 — view ticker refuses when ai.cockpit_multi_stage is false."""

    async def scenario() -> None:
        seen = []

        def runner(request):
            seen.append(request)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="should not run",
                context_reference="sha256:x",
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
            agent_cockpit_multi_stage=False,
        )
        async with app.run_test(size=(100, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            # Simulate open view ticker without full loader
            app._stage = "detail"
            app._status_note = "view ticker"
            app._focus_ticker = "BBCA"
            app._ticker_dashboard = None
            app._submit_agent_turn("what is the price?")
            await pilot.pause()
            assert seen == []

    asyncio.run(scenario())


def test_golden_view_ticker_opens_with_multi_stage_flag() -> None:
    """U5 / ADR-066 — view_ticker destination when flag on + cached dashboard."""

    async def scenario() -> None:
        from datetime import date

        from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
        from src.application.use_case.get_ticker_dashboard_use_case import (
            GetTickerDashboardUseCase,
        )
        from tests.application.use_case.test_get_ticker_dashboard_use_case import (
            FakeTickerDashboardSource,
        )

        dash = GetTickerDashboardUseCase(FakeTickerDashboardSource()).execute(
            GetTickerDashboardRequest(ticker="BBCA", brief=False, today=date(2026, 7, 24))
        )
        seen = []

        def runner(request):
            seen.append(request.stage_context)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="Ticker dashboard summary only.",
                context_reference=request.stage_context.context_reference,
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
            agent_cockpit_multi_stage=True,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._stage = "detail"
            app._status_note = "view ticker"
            app._focus_ticker = "BBCA"
            app._ticker_dashboard = dash
            app.action_focus_agent()
            await pilot.pause()
            assert app._agent_stage_open is True
            app._submit_agent_turn("Summarize price and flow")
            for _ in range(40):
                await pilot.pause(0.05)
                if seen and not app._agent_loading:
                    break
            assert len(seen) == 1
            ctx = seen[0]
            assert ctx.stage_kind.value == "view_ticker"
            assert ctx.schema_id == "tui_agent.view_ticker.v1"
            assert ctx.ticker == "BBCA"
            assert ctx.context_reference.startswith("sha256:")
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            for _ in range(20):
                await pilot.pause(0.05)
                answer = str(commentary.query_one(".agent-answer").content)
                if "dashboard" in answer.lower() or "summary" in answer.lower():
                    break
            assert "dashboard" in answer.lower() or "summary" in answer.lower()

    asyncio.run(scenario())


def test_golden_view_broker_refuses_without_multi_stage_flag() -> None:
    """U5 — broker desk refuses when ai.cockpit_multi_stage is false."""

    async def scenario() -> None:
        seen = []

        def runner(request):
            seen.append(request)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="should not run",
                context_reference="sha256:x",
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
            agent_cockpit_multi_stage=False,
        )
        async with app.run_test(size=(100, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._stage = "detail"
            app._status_note = "view broker show"
            app._broker_desk_code = "YP"
            app._broker_page = "show"
            app._broker_desk_result = object()
            app._submit_agent_turn("who is top buy?")
            await pilot.pause()
            assert seen == []

    asyncio.run(scenario())


def test_golden_view_broker_opens_with_multi_stage_flag() -> None:
    """U5 / ADR-066 — view_broker destination when flag on + desk result."""

    async def scenario() -> None:
        from datetime import date
        from decimal import Decimal
        from types import SimpleNamespace

        from src.application.services.broker_desk_from_daily_flow import DeskTickerNet
        from src.domain.entities.broker_flow import BrokerType

        def _net(ticker: str, net: str) -> DeskTickerNet:
            value = Decimal(net)
            buy = value if value > 0 else Decimal("0")
            sell = -value if value < 0 else Decimal("0")
            return DeskTickerNet(
                ticker=ticker,
                net_value=value,
                net_lot=1,
                buy_value=buy,
                sell_value=sell,
                sessions=1,
            )

        desk = SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 8, 1),
            day_net_value=Decimal("1500"),
            day_net_lot=12,
            day_ticker_count=2,
            top_buy_stocks=(_net("BBCA", "1000"),),
            top_sell_stocks=(_net("TLKM", "-500"),),
            scope_note="Tracked desk",
        )
        seen = []

        def runner(request):
            seen.append(request.stage_context)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="Broker desk summary only.",
                context_reference=request.stage_context.context_reference,
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
            agent_cockpit_multi_stage=True,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._stage = "detail"
            app._status_note = "view broker show"
            app._broker_desk_code = "YP"
            app._broker_page = "show"
            app._broker_desk_result = desk
            app._focus_ticker = "—"
            app.action_focus_agent()
            await pilot.pause()
            assert app._agent_stage_open is True
            app._submit_agent_turn("Summarize this desk day")
            for _ in range(40):
                await pilot.pause(0.05)
                if seen and not app._agent_loading:
                    break
            assert len(seen) == 1
            ctx = seen[0]
            assert ctx.stage_kind.value == "view_broker"
            assert ctx.schema_id == "tui_agent.view_broker.v1"
            assert ctx.broker_code == "YP"
            assert ctx.view == "SHOW"
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            for _ in range(20):
                await pilot.pause(0.05)
                answer = str(commentary.query_one(".agent-answer").content)
                if "desk" in answer.lower() or "summary" in answer.lower():
                    break
            assert "desk" in answer.lower() or "summary" in answer.lower()

    asyncio.run(scenario())
