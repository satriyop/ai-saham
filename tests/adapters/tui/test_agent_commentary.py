import asyncio
from dataclasses import dataclass, replace

import pytest
from textual.app import App, ComposeResult

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.agent_commentary import AgentCommentary
from src.application.dto.accumulation_agent import AgentTurnResult, AgentTurnStatus
from src.application.dto.agent_tools import (
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolProvenance,
)
from tests.adapters.tui.test_finish_cockpit_slices import _accum_payload

pytestmark = pytest.mark.agent


class _App(App[None]):
    def compose(self) -> ComposeResult:
        yield AgentCommentary(id="commentary")


@dataclass(frozen=True)
class _ToolPayload:
    schema_id: str
    value: str


def _tool_result(call_id: str, status: AgentToolExecutionStatus):
    kwargs = {
        "call_id": call_id,
        "name": AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        "status": status,
        "provenance": AgentToolProvenance("test-visible-result"),
    }
    if status is AgentToolExecutionStatus.SUCCESS:
        return AgentToolExecutionResult.create(
            **kwargs,
            data=_ToolPayload("agent_tool.visible_cockpit.result.v1", call_id),
        )
    return AgentToolExecutionResult.create(
        **kwargs,
        data=None,
        error_code="UNAVAILABLE",
        error_message="Visible result unavailable",
    )


def test_commentary_renders_answer_and_context_without_action_styling() -> None:
    async def scenario() -> None:
        app = _App()
        async with app.run_test(size=(80, 24)) as pilot:
            widget = app.query_one("#commentary", AgentCommentary)
            widget.show_result(
                AgentTurnResult(
                    status=AgentTurnStatus.SUCCESS,
                    answer="Deterministic action remains WATCH.",
                    context_reference="sha256:abc",
                    provider="deepseek",
                    model="deepseek-v4-flash",
                ),
                as_of="2026-08-01",
            )
            await pilot.pause()
            assert widget.display is True
            assert "WATCH" in str(widget.query_one(".agent-answer").content)
            assert "sha256:abc" in str(widget.query_one(".agent-meta").content)
            assert "action-enter" not in widget.classes

    asyncio.run(scenario())


def test_partial_commentary_renders_answer_and_ordered_safe_tool_trace() -> None:
    async def scenario() -> None:
        app = _App()
        async with app.run_test(size=(100, 30)) as pilot:
            widget = app.query_one("#commentary", AgentCommentary)
            first = _tool_result("first-secret-argument", AgentToolExecutionStatus.SUCCESS)
            second = _tool_result("second-secret-argument", AgentToolExecutionStatus.UNAVAILABLE)
            widget.show_result(
                AgentTurnResult(
                    status=AgentTurnStatus.PARTIAL,
                    answer="Grounded answer remains available.",
                    context_reference="sha256:context",
                    provider="deepseek",
                    model="deepseek-v4-flash",
                    warnings=("One read was unavailable",),
                    tool_results=(first, second),
                ),
                as_of="2026-08-01",
            )
            await pilot.pause()

            answer = str(widget.query_one(".agent-answer").content)
            meta = str(widget.query_one(".agent-meta").content)
            trace = str(widget.query_one(".agent-tools").content)
            assert "Grounded answer" in answer
            assert "sha256:context" in meta
            assert trace.index(first.result_reference) < trace.index(second.result_reference)
            assert "get_visible_cockpit_result · SUCCESS" in trace
            assert "get_visible_cockpit_result · UNAVAILABLE" in trace
            assert "secret-argument" not in trace

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_cockpit_dispatches_exact_judge_source_and_rejects_stale_result(size) -> None:
    async def scenario() -> None:
        seen = []

        def runner(request):
            seen.append(request.candidate)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="Commentary only.",
                context_reference="sha256:abc",
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
        async with app.run_test(size=size) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            source = app._rows[app._row_index].source
            app._submit_agent_turn("Explain the deterministic facts")
            for _ in range(20):
                await pilot.pause(0.05)
                if seen:
                    break
            assert seen == [source]
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            assert commentary.display is True
            assert app.query_one("#judge-desk").display is True
            commentary.show_loading(provider="deepseek", ticker="BBCA")
            commentary.show_result(
                AgentTurnResult(
                    status=AgentTurnStatus.SUCCESS,
                    answer="Long commentary. " * 80,
                    context_reference="sha256:long",
                    provider="deepseek",
                    model="deepseek-v4-flash",
                    warnings=("Source warning",),
                ),
                as_of="2026-08-01",
            )
            commentary.show_result(
                AgentTurnResult(
                    status=AgentTurnStatus.UNAVAILABLE,
                    error_message="Provider unavailable",
                ),
                as_of="—",
            )
            commentary.show_result(
                AgentTurnResult(
                    status=AgentTurnStatus.FAILED,
                    error_message="Provider failed",
                ),
                as_of="—",
            )
            app._rows[app._row_index] = replace(app._rows[app._row_index], source=None)
            app._submit_agent_turn("Do not dispatch limited context")
            await pilot.pause()
            assert seen == [source]
            assert "Full Judge context" in str(commentary.query_one(".agent-error").content)
            app._invalidate_agent_turn()
            await pilot.pause()
            assert commentary.display is False

    asyncio.run(scenario())
