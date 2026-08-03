"""ADR-064 multi-round orchestrator budgets and fail-closed paths."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.application.dto.accumulation_agent import (
    AgentModelResponse,
    AgentModelResponseKind,
    AgentTurnStatus,
)
from src.application.dto.agent_session import AgentSessionPolicy
from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentModelToolChoice,
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolProvenance,
    AgentToolTurnPolicy,
)
from src.application.services.agent_session_store import InMemoryAgentSessionStore
from src.application.services.agent_stage_context import build_judge_turn_request
from src.application.services.agent_tool_registry import AgentToolRegistry
from src.application.use_case.orchestrate_agent_turn_use_case import AgentTurnOrchestrator
from src.application.use_case.session_aware_agent_turn_use_case import (
    DEEPSEEK_SESSION_CERTIFICATION,
    SessionAwareAgentTurnUseCase,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


@dataclass(frozen=True)
class _Args(AgentToolArguments):
    reference: str


@dataclass(frozen=True)
class _Payload:
    schema_id: str
    value: str


class _Tool:
    def __init__(self) -> None:
        self._definition = AgentToolDefinition(
            name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
            description="Return an exact visible result.",
            argument_schema_id="agent_tool.test.args.v1",
            result_schema_id="agent_tool.test.result.v1",
            arguments=(AgentToolArgumentField("reference", "Exact result reference."),),
            required_context="VISIBLE_RESULT",
            timeout_ms=100,
            max_result_bytes=1024,
        )
        self.executed: list[str] = []

    @property
    def definition(self):
        return self._definition

    def build_arguments(self, ordered_values):
        return _Args(*ordered_values)

    def execute(self, call_id, arguments, context):
        self.executed.append(arguments.reference)
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=_Payload(self.definition.result_schema_id, "ok"),
            provenance=AgentToolProvenance("recording-fake"),
        )


class _Model:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _answer(text="WATCH remains."):
    return AgentModelResponse(text, "deepseek", "deepseek-v4-flash", finish_reason="stop")


def _tool_response(*calls):
    return AgentModelResponse(
        "",
        "deepseek",
        "deepseek-v4-flash",
        finish_reason="tool_calls",
        kind=AgentModelResponseKind.TOOL_CALLS,
        tool_calls=tuple(calls),
    )


def _call(arguments='{"reference":"sha256:abc"}', call_id="call-1"):
    return AgentModelToolCall(
        call_id,
        AgentToolName.GET_VISIBLE_COCKPIT_RESULT.value,
        arguments,
    )


def _orch(model, tool=None, *, multi_round=False, on_progress=None):
    registry = AgentToolRegistry((tool,)) if tool is not None else AgentToolRegistry()
    policy = (
        AgentToolTurnPolicy.l3(tools_enabled=True)
        if multi_round
        else AgentToolTurnPolicy.l1(tools_enabled=True)
    )
    return AgentTurnOrchestrator(
        model,
        registry,
        policy,
        on_progress=on_progress,
    )


def test_l1_flag_false_keeps_two_provider_calls_and_one_batch() -> None:
    tool = _Tool()
    model = _Model([_tool_response(_call()), _answer()])
    result = _orch(model, tool, multi_round=False).execute(
        build_judge_turn_request("why?", make_candidate())
    )
    assert result.status is AgentTurnStatus.SUCCESS
    assert len(model.requests) == 2
    assert model.requests[0].tool_choice is AgentModelToolChoice.AUTO
    assert model.requests[1].tool_choice is AgentModelToolChoice.NONE
    assert len(tool.executed) == 1


def test_l3_enforces_three_rounds_and_forced_final_none() -> None:
    tool = _Tool()
    # Round1 tools, round2 tools (different args), round3 must be forced none.
    model = _Model(
        [
            _tool_response(_call('{"reference":"sha256:aaa"}', "c1")),
            _tool_response(_call('{"reference":"sha256:bbb"}', "c2")),
            _answer("Final after two hops."),
        ]
    )
    progress: list[str] = []
    result = _orch(model, tool, multi_round=True, on_progress=progress.append).execute(
        build_judge_turn_request("research path", make_candidate())
    )
    assert result.status is AgentTurnStatus.SUCCESS
    assert "Final after two hops" in result.answer
    assert len(model.requests) == 3
    assert model.requests[0].tool_choice is AgentModelToolChoice.AUTO
    assert model.requests[1].tool_choice is AgentModelToolChoice.AUTO
    assert model.requests[2].tool_choice is AgentModelToolChoice.NONE
    assert len(tool.executed) == 2
    assert any("round 1/3" in p for p in progress)
    assert any("tool get_visible_cockpit_result" in p for p in progress)


def test_l3_tool_budget_four_then_forced_final() -> None:
    tool = _Tool()
    # Four tools across two batches of two, then final must be none even if rounds remain.
    model = _Model(
        [
            _tool_response(
                _call('{"reference":"sha256:a1"}', "a1"),
                _call('{"reference":"sha256:a2"}', "a2"),
            ),
            _tool_response(
                _call('{"reference":"sha256:a3"}', "a3"),
                _call('{"reference":"sha256:a4"}', "a4"),
            ),
            _answer("Done at tool cap."),
        ]
    )
    result = _orch(model, tool, multi_round=True).execute(
        build_judge_turn_request("cap tools", make_candidate())
    )
    assert result.status is AgentTurnStatus.SUCCESS
    assert len(tool.executed) == 4
    assert model.requests[-1].tool_choice is AgentModelToolChoice.NONE


def test_l3_invalid_batch_fails_closed_without_execute() -> None:
    tool = _Tool()
    model = _Model(
        [
            _tool_response(
                _call('{"reference":"sha256:x"}', "d1"),
                _call('{"reference":"sha256:x"}', "d2"),  # duplicate canonical args
            )
        ]
    )
    result = _orch(model, tool, multi_round=True).execute(
        build_judge_turn_request("bad batch", make_candidate())
    )
    assert result.status is AgentTurnStatus.FAILED
    assert (
        "invalid tool batch" in (result.error_message or "").lower()
        or "duplicate" in (result.error_message or "").lower()
    )
    assert tool.executed == []


def test_l3_duplicate_across_rounds_fails_closed() -> None:
    tool = _Tool()
    same = _call('{"reference":"sha256:same"}', "r1")
    model = _Model(
        [
            _tool_response(same),
            _tool_response(AgentModelToolCall("r2", same.name, same.arguments_json)),
        ]
    )
    result = _orch(model, tool, multi_round=True).execute(
        build_judge_turn_request("dup turn", make_candidate())
    )
    assert result.status is AgentTurnStatus.FAILED
    assert "duplicate" in (result.error_message or "").lower()
    assert tool.executed == ["sha256:same"]


def test_l3_exhaustion_without_answer_failed() -> None:
    tool = _Tool()
    # Always tool_calls until forced final then empty answer path via tool_calls on final
    model = _Model(
        [
            _tool_response(_call('{"reference":"sha256:e1"}', "e1")),
            _tool_response(_call('{"reference":"sha256:e2"}', "e2")),
            _tool_response(_call('{"reference":"sha256:e3"}', "e3")),  # on forced final → fail
        ]
    )
    result = _orch(model, tool, multi_round=True).execute(
        build_judge_turn_request("no answer", make_candidate())
    )
    assert result.status is AgentTurnStatus.FAILED
    assert "final" in (result.error_message or "").lower()


def test_l3_failed_turn_does_not_commit_session_memory() -> None:
    tool = _Tool()
    model = _Model(
        [
            _tool_response(
                _call('{"reference":"sha256:x"}', "d1"),
                _call('{"reference":"sha256:x"}', "d2"),
            )
        ]
    )
    inner = _orch(model, tool, multi_round=True)
    store = InMemoryAgentSessionStore(AgentSessionPolicy(enabled=True))
    uc = SessionAwareAgentTurnUseCase(
        inner,
        store,
        AgentSessionPolicy(enabled=True),
        certification=DEEPSEEK_SESSION_CERTIFICATION,
        configured_provider="deepseek",
    )
    candidate = make_candidate()
    # Seed one successful turn first
    ok_model = _Model([_answer("seed")])
    ok_inner = _orch(ok_model, tool, multi_round=True)
    ok_uc = SessionAwareAgentTurnUseCase(
        ok_inner,
        store,
        AgentSessionPolicy(enabled=True),
        certification=DEEPSEEK_SESSION_CERTIFICATION,
        configured_provider="deepseek",
    )
    seed = ok_uc.execute(build_judge_turn_request("seed", candidate))
    assert seed.status is AgentTurnStatus.SUCCESS
    before = store.get()
    assert before is not None
    before_commentary = len(before.commentary_turns)
    before_tools = len(before.tool_records)

    failed = uc.execute(build_judge_turn_request("fail me", candidate))
    assert failed.status is AgentTurnStatus.FAILED
    after = store.get()
    assert after is not None
    assert len(after.commentary_turns) == before_commentary
    assert len(after.tool_records) == before_tools
    assert after.in_flight is False


def test_progress_callback_not_treated_as_success_answer() -> None:
    tool = _Tool()
    model = _Model([_tool_response(_call()), _answer("real")])
    progress: list[str] = []
    result = _orch(model, tool, multi_round=True, on_progress=progress.append).execute(
        build_judge_turn_request("q", make_candidate())
    )
    assert result.status is AgentTurnStatus.SUCCESS
    assert result.answer == "real"
    assert all("real" not in p for p in progress)
