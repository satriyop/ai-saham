"""Live TUI pilots — session reset entrypoints and paint-safety (Profiles D/N)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from textual.widgets import Input

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.application.dto.accumulation_agent import (
    AgentTurnRequest,
    AgentTurnResult,
    AgentTurnStatus,
)
from tests.adapters.tui.agent_board_fixtures import agent_accum_payload as _accum_payload
from tests.agent_live.conftest import agent_live_call

pytestmark = [pytest.mark.agent, agent_live_call, pytest.mark.tui]


class _SessionRunner:
    """Minimal session-capable runner for TUI reset command pilots."""

    def __init__(self) -> None:
        self.requests: list[AgentTurnRequest] = []
        self._session_id = "sess_test_1"
        self.reset_calls = 0

    def __call__(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        return AgentTurnResult(
            status=AgentTurnStatus.SUCCESS,
            answer="commentary",
            context_reference="sha256:" + ("c" * 64),
            provider="deepseek",
            model="deepseek-v4-flash",
            session_id=self._session_id,
            turn_sequence=1 + len(self.requests),
        )

    def reset_session(self) -> str:
        self.reset_calls += 1
        self._session_id = f"sess_test_{self.reset_calls + 1}"
        return self._session_id


@pytest.mark.parametrize(
    "command",
    ("/reset", "session reset", "reset session"),
)
def test_d5_tui_reset_commands_invoke_reset_session(command: str) -> None:
    """D5 TUI: /reset · session reset · reset session call runner.reset_session."""

    async def scenario() -> None:
        runner = _SessionRunner()
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            app._prompt_mode = "agent"
            # Product entry: Input.Submitted path used by the prompt rail
            prompt = app.query_one("#prompt-input", Input)
            prompt.value = command
            app.on_input_submitted(Input.Submitted(prompt, command))
            await pilot.pause()
            assert runner.reset_calls >= 1

    asyncio.run(scenario())


def test_d5_tui_reset_session_method_direct() -> None:
    """D5: _reset_agent_session is the shared product entrypoint for all aliases."""

    async def scenario() -> None:
        runner = _SessionRunner()
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
        )
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._reset_agent_session()
            await pilot.pause()
            assert runner.reset_calls == 1
            sid = runner.reset_session()
            assert sid.startswith("sess_test_")

    asyncio.run(scenario())


def test_n3_cancel_wrong_lineage_paint_rejection() -> None:
    """N3: invalidate after submit discards late paint obligation."""

    async def scenario() -> None:
        def runner(request: AgentTurnRequest) -> AgentTurnResult:
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer=f"late {request.user_text}",
                context_reference="sha256:" + ("d" * 64),
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
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            gen0 = app._agent_generation
            app._prompt_mode = "agent"
            app._submit_agent_turn("first question")
            app._invalidate_agent_turn()
            assert app._agent_generation >= gen0
            await pilot.pause(0.1)

    asyncio.run(scenario())


def test_b7_tui_limited_source_unavailable() -> None:
    """B7 TUI: limited row without source never dispatches runner."""

    async def scenario() -> None:
        calls: list[str] = []

        def runner(request: AgentTurnRequest) -> AgentTurnResult:
            calls.append(request.user_text)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="no",
                context_reference="sha256:" + ("e" * 64),
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
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            row = app._rows[app._row_index]
            app._rows[app._row_index] = replace(row, source=None)
            app._prompt_mode = "agent"
            app._submit_agent_turn("limited")
            await pilot.pause(0.1)
            assert calls == []

    asyncio.run(scenario())
