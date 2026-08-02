from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import AgentToolExecutionStatus
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_accumulation_judge_tool import (
    AccumulationJudgeArguments,
    AccumulationJudgeResultData,
    AccumulationJudgeTool,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _visible_context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _workflow_result(*candidates, warnings=()):
    return SimpleNamespace(
        single_projection=SimpleNamespace(candidates=list(candidates)),
        warnings=tuple(warnings),
    )


def test_judge_tool_wraps_existing_bounded_context() -> None:
    candidate = make_candidate()
    tool = AccumulationJudgeTool(
        lambda ticker: _workflow_result(candidate, warnings=("workflow warning",))
    )

    result = tool.execute(
        "judge-1",
        AccumulationJudgeArguments("BBCA"),
        _visible_context(),
    )

    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, AccumulationJudgeResultData)
    assert result.data.schema_id == "agent_tool.accum_judge.result.v1"
    assert result.data.judgment.schema_id == "tui_agent.accum_judge.v1"
    assert result.data.judgment.ticker == "BBCA"
    assert result.source_reference == result.data.judgment.context_reference
    assert result.provenance.source == "accumulation-screen-read-only"
    assert "workflow warning" in result.warnings
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_no_candidate_is_unavailable() -> None:
    tool = AccumulationJudgeTool(lambda ticker: _workflow_result())

    result = tool.execute(
        "judge-empty",
        AccumulationJudgeArguments("BBCA"),
        _visible_context(),
    )

    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
    assert result.error_code == "ACCUMULATION_JUDGMENT_UNAVAILABLE"


@pytest.mark.parametrize(
    "candidates",
    (
        (make_candidate(), make_candidate()),
        (replace(make_candidate(), ticker="TLKM"),),
    ),
)
def test_candidate_count_or_identity_disagreement_fails(candidates) -> None:
    tool = AccumulationJudgeTool(lambda ticker: _workflow_result(*candidates))

    result = tool.execute(
        "judge-invariant",
        AccumulationJudgeArguments("BBCA"),
        _visible_context(),
    )

    assert result.status is AgentToolExecutionStatus.FAILED
    assert result.error_code == "ACCUMULATION_JUDGMENT_INVARIANT"


def test_projection_invariant_error_fails_without_raw_details() -> None:
    candidate = make_candidate(trade_ticker="TLKM")
    tool = AccumulationJudgeTool(lambda ticker: _workflow_result(candidate))

    result = tool.execute(
        "judge-context-invariant",
        AccumulationJudgeArguments("BBCA"),
        _visible_context(),
    )

    assert result.status is AgentToolExecutionStatus.FAILED
    assert result.error_code == "ACCUMULATION_JUDGMENT_INVARIANT"
    assert "TLKM" not in (result.error_message or "")


def test_workflow_exception_fails_without_path_or_sql_copy() -> None:
    def _broken(ticker):
        raise RuntimeError(f"/private/data.db SQL secret for {ticker}")

    result = AccumulationJudgeTool(_broken).execute(
        "judge-broken",
        AccumulationJudgeArguments("BBCA"),
        _visible_context(),
    )

    assert result.status is AgentToolExecutionStatus.FAILED
    assert result.error_code == "ACCUMULATION_JUDGMENT_FAILED"
    assert "/private" not in (result.error_message or "")
    assert "SQL" not in (result.error_message or "")


@pytest.mark.parametrize(
    "ticker",
    ("", "bbca", " BBCA", "BBCA ", "BBCA.JK", "^JKSE", "BBCA1", "ABC"),
)
def test_ticker_argument_rejects_noncanonical_values(ticker: str) -> None:
    with pytest.raises(ValueError, match="canonical four-letter"):
        AccumulationJudgeArguments(ticker)


def test_definition_locks_schema_budget_and_single_argument() -> None:
    tool = AccumulationJudgeTool(lambda ticker: _workflow_result())

    assert tool.definition.argument_schema_id == "agent_tool.accum_judge.args.v1"
    assert tool.definition.result_schema_id == "agent_tool.accum_judge.result.v1"
    assert tuple(field.name for field in tool.definition.arguments) == ("ticker",)
    assert tool.definition.timeout_ms == 12_000
    assert tool.definition.max_result_bytes == 32 * 1024
