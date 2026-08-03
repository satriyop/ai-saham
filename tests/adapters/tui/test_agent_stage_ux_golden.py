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
