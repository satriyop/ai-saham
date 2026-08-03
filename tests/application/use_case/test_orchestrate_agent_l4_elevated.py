"""ADR-065 elevated/external confirm, gaps, deny, and fail-safe flags."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.application.dto.accumulation_agent import (
    AgentModelResponse,
    AgentModelResponseKind,
    AgentTurnStatus,
)
from src.application.dto.agent_tools import (
    AgentApprovalRequest,
    AgentModelToolCall,
    AgentModelToolChoice,
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolProvenance,
    AgentToolSideEffect,
    AgentToolTurnPolicy,
)
from src.application.services.agent_ro_data_query_tool import RoDataQueryTool
from src.application.services.agent_stage_context import build_judge_turn_request
from src.application.services.agent_tool_registry import AgentToolRegistry
from src.application.services.agent_web_research_tool import (
    NullWebResearchClient,
    WebResearchSnippet,
    WebResearchTool,
)
from src.application.use_case.orchestrate_agent_turn_use_case import AgentTurnOrchestrator
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


@dataclass(frozen=True)
class _Args(AgentToolArguments):
    reference: str


@dataclass(frozen=True)
class _Payload:
    schema_id: str
    value: str


class _LocalTool:
    def __init__(self) -> None:
        self._definition = AgentToolDefinition(
            name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
            description="local",
            argument_schema_id="a",
            result_schema_id="r",
            arguments=(AgentToolArgumentField("reference", "ref"),),
            required_context="VIS",
            timeout_ms=100,
            max_result_bytes=1024,
        )
        self.executed = 0

    @property
    def definition(self):
        return self._definition

    def build_arguments(self, ordered_values):
        return _Args(ordered_values[0])

    def execute(self, call_id, arguments, context):
        self.executed += 1
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=_Payload("r", "ok"),
            provenance=AgentToolProvenance("local"),
        )


class _Model:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _answer(text="ok"):
    return AgentModelResponse(text, "deepseek", "deepseek-v4-flash", finish_reason="stop")


def _tools(*calls):
    return AgentModelResponse(
        "",
        "deepseek",
        "deepseek-v4-flash",
        finish_reason="tool_calls",
        kind=AgentModelResponseKind.TOOL_CALLS,
        tool_calls=tuple(calls),
    )


class _WebOk:
    def research(self, query: str, *, max_results: int):
        snip = WebResearchSnippet("T", "https://example.com", f"about {query}")
        return (snip,)[:max_results]


class _WebCounting:
    """Web client that would succeed — counts calls to prove it never ran."""

    def __init__(self) -> None:
        self.calls = 0

    def research(self, query: str, *, max_results: int):
        self.calls += 1
        snip = WebResearchSnippet("T", "https://example.com", f"about {query}")
        return (snip,)[:max_results]


class _DenyThenApprove:
    """Deny the first confirm, approve every one after (stateful operator)."""

    def __init__(self) -> None:
        self.seen = 0

    def __call__(self, req: AgentApprovalRequest) -> bool:
        self.seen += 1
        return self.seen >= 2


def test_web_research_requires_confirm_and_counts_as_tool() -> None:
    web = WebResearchTool(_WebOk())  # type: ignore[arg-type]
    local = _LocalTool()
    model = _Model(
        [
            _tools(
                AgentModelToolCall("w1", "web_research", '{"query":"BBCA news"}'),
            ),
            _answer("Used external research."),
        ]
    )
    approvals: list[AgentApprovalRequest] = []

    def on_approval(req: AgentApprovalRequest) -> bool:
        approvals.append(req)
        return True

    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((local, web)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
        on_approval=on_approval,
    )
    result = orch.execute(build_judge_turn_request("news?", make_candidate()))
    assert result.status is AgentTurnStatus.SUCCESS
    assert len(approvals) == 1
    assert approvals[0].tool_name == "web_research"
    assert "Network" in approvals[0].implication
    assert any(r.name is AgentToolName.WEB_RESEARCH for r in result.tool_results)
    assert result.elevated_attempted is True
    assert any("EXTERNAL_RESEARCH" in w for w in result.warnings)


def test_deny_skips_elevated_and_continues() -> None:
    web = WebResearchTool(_WebOk())  # type: ignore[arg-type]
    model = _Model(
        [
            _tools(AgentModelToolCall("w1", "web_research", '{"query":"x"}')),
            _answer("Answered without external."),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((web,)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
        on_approval=lambda _r: False,
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert result.status is AgentTurnStatus.PARTIAL  # denied tool non-success
    assert result.tool_results[0].error_code == "TOOL_DENIED"
    assert result.answer.startswith("Answered")


def test_unregistered_tool_emits_gap_clue_not_fake_execute() -> None:
    local = _LocalTool()
    model = _Model(
        [
            _tools(AgentModelToolCall("g1", "magic_sql_dump", '{"q":"x"}')),
            _answer("No invented tool ran."),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((local,)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert result.status is AgentTurnStatus.SUCCESS
    assert result.gap_clues
    assert result.gap_clues[0].code == "TOOL_GAP"
    assert any("TOOL_GAP" in w for w in result.warnings)
    assert local.executed == 0


def test_post_approve_web_fail_sets_restore_flag() -> None:
    web = WebResearchTool(NullWebResearchClient())
    model = _Model(
        [
            _tools(AgentModelToolCall("w1", "web_research", '{"query":"x"}')),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((web,)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
        on_approval=lambda _r: True,
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert result.status is AgentTurnStatus.FAILED
    assert result.restore_last_good is True
    assert result.elevated_attempted is True


def test_ro_data_query_allowlist_and_confirm(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "ro.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE candles (ticker TEXT, date TEXT, close REAL, volume REAL)")
        conn.execute("INSERT INTO candles VALUES ('BBCA','2026-08-01',100.0,1.0)")
        conn.commit()
    tool = RoDataQueryTool(db)
    model = _Model(
        [
            _tools(
                AgentModelToolCall(
                    "r1",
                    "ro_data_query",
                    '{"shape":"TICKER_LATEST_CLOSE","subject":"BBCA"}',
                )
            ),
            _answer("local rows"),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((tool,)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
        on_approval=lambda _r: True,
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert result.status is AgentTurnStatus.SUCCESS
    assert result.tool_results[0].status is AgentToolExecutionStatus.SUCCESS
    assert result.tool_results[0].side_effect is AgentToolSideEffect.LOCAL_READ_ELEVATED


def test_elevated_counts_toward_l3_tool_budget() -> None:
    web = WebResearchTool(_WebOk())  # type: ignore[arg-type]
    # Force four web research calls across two batches (each needs confirm).
    model = _Model(
        [
            _tools(
                AgentModelToolCall("a", "web_research", '{"query":"1"}'),
                AgentModelToolCall("b", "web_research", '{"query":"2"}'),
            ),
            _tools(
                AgentModelToolCall("c", "web_research", '{"query":"3"}'),
                AgentModelToolCall("d", "web_research", '{"query":"4"}'),
            ),
            _answer("cap"),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((web,)),
        AgentToolTurnPolicy.l3(tools_enabled=True),
        on_approval=lambda _r: True,
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert result.status is AgentTurnStatus.SUCCESS
    assert len(result.tool_results) == 4
    assert model.requests[-1].tool_choice is AgentModelToolChoice.NONE


def test_no_approver_fails_closed_and_continues() -> None:
    """F2: elevated PER_CALL tool + no approval callback must NOT execute."""
    client = _WebCounting()
    web = WebResearchTool(client)  # type: ignore[arg-type]
    model = _Model(
        [
            _tools(AgentModelToolCall("w1", "web_research", '{"query":"x"}')),
            _answer("Answered from Judge context only."),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((web,)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
        # No on_approval anywhere: a missing approver is not consent.
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert client.calls == 0  # never executed — no network egress
    assert result.status is AgentTurnStatus.PARTIAL
    assert result.tool_results[0].error_code == "TOOL_NO_APPROVER"
    assert result.tool_results[0].status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.answer.startswith("Answered")
    assert result.elevated_attempted is True


def test_side_effect_none_tool_runs_without_approver() -> None:
    """F2 boundary: ordinary OUR tools still run with no approval callback."""
    local = _LocalTool()
    model = _Model(
        [
            _tools(AgentModelToolCall("g1", "get_visible_cockpit_result", '{"reference":"r"}')),
            _answer("Used the visible result."),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((local,)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert local.executed == 1
    assert result.status is AgentTurnStatus.SUCCESS


def test_typeerror_midturn_fails_once_without_rerun() -> None:
    """F1: a genuine TypeError mid-turn maps to FAILED and never re-runs."""
    local = _LocalTool()

    class _RaiseOnSecond:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            if self.calls == 1:
                return _tools(
                    AgentModelToolCall("g1", "get_visible_cockpit_result", '{"reference":"r"}')
                )
            raise TypeError("boom mid-turn")

    model = _RaiseOnSecond()
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((local,)),
        AgentToolTurnPolicy.l1(tools_enabled=True),
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert result.status is AgentTurnStatus.FAILED
    assert local.executed == 1  # tool ran exactly once — no restart
    assert model.calls == 2  # first (tool_calls) + second (raises); no re-run


def test_deny_then_different_tool_continues_and_executes() -> None:
    """F3: a deny skips-and-continues; a different OUR tool still executes."""
    web = WebResearchTool(_WebOk())  # type: ignore[arg-type]
    local = _LocalTool()
    model = _Model(
        [
            _tools(
                AgentModelToolCall("w1", "web_research", '{"query":"x"}'),
                AgentModelToolCall("g1", "get_visible_cockpit_result", '{"reference":"r"}'),
            ),
            _answer("Answered with the local result only."),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((web, local)),
        AgentToolTurnPolicy.l3(tools_enabled=True),
        on_approval=lambda _r: False,  # deny the elevated call
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    assert result.status is AgentTurnStatus.PARTIAL  # deny is non-success
    assert local.executed == 1  # different tool still ran after the deny
    codes = [r.error_code for r in result.tool_results]
    assert "TOOL_DENIED" in codes  # deny kept in the trace for honesty
    assert result.answer.startswith("Answered")


def test_deny_then_repropose_same_tool_is_not_duplicate() -> None:
    """F3: a denied tool's identity is not seeded, so re-proposal is allowed."""
    client = _WebCounting()
    web = WebResearchTool(client)  # type: ignore[arg-type]
    model = _Model(
        [
            _tools(AgentModelToolCall("w1", "web_research", '{"query":"x"}')),
            _tools(AgentModelToolCall("w2", "web_research", '{"query":"x"}')),  # same args
            _answer("Second attempt was approved."),
        ]
    )
    orch = AgentTurnOrchestrator(
        model,
        AgentToolRegistry((web,)),
        AgentToolTurnPolicy.l3(tools_enabled=True),
        on_approval=_DenyThenApprove(),
    )
    result = orch.execute(build_judge_turn_request("q", make_candidate()))
    # Old behavior failed the turn here as a duplicate tool call.
    assert result.status is AgentTurnStatus.PARTIAL
    assert client.calls == 1  # executed exactly once (the approved re-proposal)
    assert not any("duplicate" in (w or "").lower() for w in result.warnings)
    codes = [r.error_code for r in result.tool_results]
    assert codes.count("TOOL_DENIED") == 1  # first attempt denied, in trace
    assert result.answer.startswith("Second attempt")


def test_composition_registers_elevated_only_with_flags(monkeypatch, tmp_path) -> None:
    from src.infrastructure.composition import agent_model as am
    from src.infrastructure.composition.agent_model import build_agent_composition
    from src.infrastructure.config.app_config import AiConfig

    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(am, "DeepSeekAgentModel", lambda key: object())
    db = tmp_path / "x.db"
    db.touch()

    plain = build_agent_composition(
        AiConfig(enabled=True, tools_enabled=True, provider="deepseek"),
        db_path=db,
    )
    assert AgentToolName.WEB_RESEARCH not in plain.registered_tools
    assert AgentToolName.RO_DATA_QUERY not in plain.registered_tools

    elev = build_agent_composition(
        AiConfig(
            enabled=True,
            tools_enabled=True,
            external_tools=True,
            web_research=True,
            ro_data_query=True,
            provider="deepseek",
        ),
        db_path=db,
    )
    assert AgentToolName.WEB_RESEARCH in elev.registered_tools
    assert AgentToolName.RO_DATA_QUERY in elev.registered_tools
    assert elev.external_tools is True
