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
from tests.adapters.tui.agent_board_fixtures import agent_accum_payload as _accum_payload

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
                    warnings=(
                        "Risk snapshot 2026-07-31 differs from decision as-of 2026-08-03",
                        "SESSION_ALIGNED_LATE_WITHIN_LAG",
                    ),
                ),
                as_of="2026-08-01",
                ticker="UNVR",
            )
            await pilot.pause()
            assert widget.display is True
            assert "WATCH" in str(widget.query_one(".agent-answer").content)
            assert "sha256:abc" in str(widget.query_one(".agent-meta").content)
            status = str(widget.query_one(".agent-status").content)
            assert "Turn  OK · UNVR" in status
            assert "RISK_SNAPSHOT_LAG" in status or "Risk lag" in status
            assert "action-enter" not in widget.classes

    asyncio.run(scenario())


def test_stage_mode_keeps_answer_primary_and_compacts_honesty() -> None:
    """Stage: chips-only status; Do guides under more; long answer still renders."""

    async def scenario() -> None:
        app = _App()
        async with app.run_test(size=(100, 30)) as pilot:
            widget = app.query_one("#commentary", AgentCommentary)
            widget.set_stage_mode(True)
            long_answer = "Fakta deterministik — top akumulator (net buy):\n" + "\n".join(
                f"{i}. YP net {i * 1000}" for i in range(1, 16)
            )
            widget.show_result(
                AgentTurnResult(
                    status=AgentTurnStatus.SUCCESS,
                    answer=long_answer,
                    context_reference="sha256:ctx",
                    provider="deepseek",
                    model="deepseek-v4-flash",
                    warnings=(
                        "Risk snapshot 2026-07-31 differs from decision as-of 2026-08-03",
                        "Incomplete signal authority coverage — not source-authoritative",
                        "bandar_detector",
                        "SESSION_ALIGNED_LATE_WITHIN_LAG",
                    ),
                ),
                as_of="2026-08-03",
                ticker="ICBP",
                question="broker apa saja yang sedang mengakumulasi?",
            )
            await pilot.pause()
            status = str(widget.query_one(".agent-status").content)
            more = str(widget.query_one(".agent-more").content)
            answer = str(widget.query_one(".agent-answer").content)
            # Compact header: no multi-line Do guides
            assert "Turn  OK · ICBP" in status
            assert "AUTHORITY_INCOMPLETE:" not in status
            assert "secondary" not in status.lower()
            # Guides still available under more
            assert "Honesty guides" in more
            assert "Do:" in more
            # Full answer content is in the answer widget (not clipped by paint)
            assert "Top akumulator" in answer or "top akumulator" in answer.lower()
            assert "YP net 15000" in answer
            # Stage CSS gives the answer scroll a real share of height
            css = AgentCommentary.DEFAULT_CSS
            assert "min-height: 12" in css or "min-height:12" in css.replace(" ", "")

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
            seen.append(request.stage_context)
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
            from src.application.services.agent_accumulation_context import (
                build_agent_accumulation_context,
            )

            assert len(seen) == 1
            assert (
                seen[0].context_reference
                == build_agent_accumulation_context(source).context_reference
            )
            assert seen[0].ticker == source.ticker
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            assert commentary.display is True
            # OpenCode-style stage replace: Judge is hidden while agent is open.
            assert app.query_one("#judge-desk").display is False
            assert app._agent_stage_open is True
            commentary.show_loading(provider="deepseek", ticker="BBCA", question="q")
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
                question="q",
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
            # Limited/missing source must not dispatch another turn.
            assert len(seen) == 1
            assert "Full Judge context" in str(commentary.query_one(".agent-error").content)
            app._invalidate_agent_turn()
            await pilot.pause()
            assert commentary.display is False
            assert app._agent_stage_open is False

    asyncio.run(scenario())


def test_free_text_auto_enters_agent_mode_and_slash_opens_stage() -> None:
    async def scenario() -> None:
        seen = []

        def runner(request):
            seen.append(request.user_text)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="ok",
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
        async with app.run_test(size=(100, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            assert app._prompt_mode == "idle"
            app.action_focus_agent()
            assert app._prompt_mode == "agent"
            assert app._agent_stage_open is True
            assert app.query_one("#judge-desk").display is False
            commentary = app.query_one("#agent-commentary", AgentCommentary)
            assert commentary.display is True
            # Free text from idle still auto-routes to agent (without mode agent first).
            app._prompt_mode = "idle"
            app._agent_stage_open = False
            app._submit_agent_turn = app._submit_agent_turn  # keep real
            # Simulate Input.Submitted path via on_input_submitted contract:
            from textual.widgets import Input

            inp = app.query_one("#prompt-input", Input)
            inp.value = "Why is this ENTER?"
            app.on_input_submitted(Input.Submitted(inp, inp.value))
            for _ in range(20):
                await pilot.pause(0.05)
                if seen:
                    break
            assert app._prompt_mode == "agent"
            assert seen == ["Why is this ENTER?"]
            assert app._agent_stage_open is True

    asyncio.run(scenario())
