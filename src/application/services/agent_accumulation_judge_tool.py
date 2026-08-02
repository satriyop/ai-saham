"""Bounded agent projection of canonical single-ticker accumulation judgment."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from src.application.dto.accumulation_agent import AgentAccumulationContext
from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolFreshness,
    AgentToolName,
    AgentToolProvenance,
)
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
    build_agent_accumulation_context,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowResult,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.accum_judge.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.accum_judge.result.v1"


@dataclass(frozen=True)
class AccumulationJudgeArguments(AgentToolArguments):
    ticker: str

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")


@dataclass(frozen=True)
class AccumulationJudgeResultData:
    schema_id: str
    judgment: AgentAccumulationContext


class AccumulationJudgeTool:
    """Execute the canonical read-only workflow and return its bounded context."""

    _definition = AgentToolDefinition(
        name=AgentToolName.JUDGE_ACCUMULATION_TICKER,
        description="Return the canonical local accumulation judgment for one ticker.",
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
        ),
        required_context="LOCAL_ACCUMULATION_SCREEN_CACHE",
        timeout_ms=12_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(
        self,
        judge_ticker: Callable[[str], RunAccumulationScreenWorkflowResult],
    ) -> None:
        self._judge_ticker = judge_ticker

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> AccumulationJudgeArguments:
        if len(ordered_values) != 1:
            raise ValueError("accumulation judge tool requires exactly one argument")
        return AccumulationJudgeArguments(ordered_values[0])

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, AccumulationJudgeArguments):
            raise TypeError("accumulation judge tool received the wrong argument type")
        ticker = arguments.ticker
        base_provenance = AgentToolProvenance(
            source="accumulation-screen-read-only",
            source_reference=f"accumulation-judge:{ticker}",
        )
        try:
            result = self._judge_ticker(ticker)
            projection = result.single_projection
            candidates = tuple(projection.candidates) if projection is not None else ()
            if not candidates:
                return _error_result(
                    call_id=call_id,
                    status=AgentToolExecutionStatus.UNAVAILABLE,
                    code="ACCUMULATION_JUDGMENT_UNAVAILABLE",
                    message="No canonical accumulation candidate is available for this ticker.",
                    provenance=base_provenance,
                )
            if len(candidates) != 1 or candidates[0].ticker != ticker:
                return _error_result(
                    call_id=call_id,
                    status=AgentToolExecutionStatus.FAILED,
                    code="ACCUMULATION_JUDGMENT_INVARIANT",
                    message="The canonical accumulation result failed its identity checks.",
                    provenance=base_provenance,
                )
            judgment = build_agent_accumulation_context(candidates[0])
        except AgentContextUnavailableError:
            return _error_result(
                call_id=call_id,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                code="ACCUMULATION_JUDGMENT_UNAVAILABLE",
                message="The full canonical accumulation judgment is unavailable.",
                provenance=base_provenance,
            )
        except AgentContextInvariantError:
            return _error_result(
                call_id=call_id,
                status=AgentToolExecutionStatus.FAILED,
                code="ACCUMULATION_JUDGMENT_INVARIANT",
                message="The canonical accumulation result failed its identity checks.",
                provenance=base_provenance,
            )
        except Exception:
            return _error_result(
                call_id=call_id,
                status=AgentToolExecutionStatus.FAILED,
                code="ACCUMULATION_JUDGMENT_FAILED",
                message="The local accumulation judgment failed safely.",
                provenance=base_provenance,
            )

        warnings = tuple(dict.fromkeys((*result.warnings, *judgment.warnings)))
        freshness_status = (
            judgment.freshness.alignment_state if judgment.freshness is not None else "UNKNOWN"
        )
        provenance = AgentToolProvenance(
            source="accumulation-screen-read-only",
            as_of=judgment.as_of,
            source_reference=judgment.context_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=AgentToolName.JUDGE_ACCUMULATION_TICKER,
            status=AgentToolExecutionStatus.SUCCESS,
            data=AccumulationJudgeResultData(
                schema_id=_RESULT_SCHEMA_ID,
                judgment=judgment,
            ),
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=judgment.as_of,
                status=freshness_status,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=judgment.context_reference,
        )


def _error_result(
    *,
    call_id: str,
    status: AgentToolExecutionStatus,
    code: str,
    message: str,
    provenance: AgentToolProvenance,
) -> AgentToolExecutionResult:
    return AgentToolExecutionResult.create(
        call_id=call_id,
        name=AgentToolName.JUDGE_ACCUMULATION_TICKER,
        status=status,
        data=None,
        error_code=code,
        error_message=message,
        provenance=provenance,
        source_reference=provenance.source_reference,
    )
