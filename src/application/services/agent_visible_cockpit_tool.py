"""Read-only projection of the exact cockpit stage result visible this turn."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from src.application.dto.accumulation_agent import (
    AgentAccumulationContext,
    AgentStageContext,
    AgentStageKind,
)
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

_REFERENCE_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_ARGUMENT_SCHEMA_ID = "agent_tool.visible_cockpit.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.visible_cockpit.result.v1"

_RESULT_KIND_BY_STAGE: dict[AgentStageKind, str] = {
    AgentStageKind.ACCUM_JUDGE: "ACCUMULATION_JUDGE",
    AgentStageKind.ACCUM_SCREEN: "ACCUMULATION_SCREEN",
    AgentStageKind.VIEW_TICKER: "VIEW_TICKER",
    AgentStageKind.VIEW_BROKER: "VIEW_BROKER",
    AgentStageKind.PREOPEN_SCREEN: "PREOPEN_SCREEN",
    AgentStageKind.PLAN_SWING: "PLAN_SWING",
}


@dataclass(frozen=True)
class VisibleCockpitResultArguments(AgentToolArguments):
    visible_result_reference: str

    def __post_init__(self) -> None:
        if _REFERENCE_PATTERN.fullmatch(self.visible_result_reference) is None:
            raise ValueError("visible result reference must be canonical sha256")


@dataclass(frozen=True)
class VisibleCockpitResultData:
    """One polymorphic visible-result envelope (ADR-066 D2)."""

    schema_id: str
    result_kind: str
    context: AgentStageContext

    def __post_init__(self) -> None:
        if not self.schema_id.strip():
            raise ValueError("visible cockpit result requires schema_id")
        if not self.result_kind.strip():
            raise ValueError("visible cockpit result requires result_kind")
        expected = _RESULT_KIND_BY_STAGE.get(self.context.stage_kind)
        if expected is not None and self.result_kind != expected:
            raise ValueError(
                f"result_kind {self.result_kind!r} does not match "
                f"stage_kind {self.context.stage_kind.value!r}"
            )
        if self.context.schema_id.strip() == "":
            raise ValueError("stage context requires schema_id")


class VisibleCockpitResultTool:
    """Return only the exact stage context captured in the invocation context."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        description="Return the exact deterministic cockpit stage result visible in this turn.",
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "visible_result_reference",
                "Exact sha256 reference supplied with the current visible result.",
            ),
        ),
        required_context="VISIBLE_COCKPIT_RESULT",
        timeout_ms=100,
        max_result_bytes=32 * 1024,
    )

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(
        self,
        ordered_values: tuple[str, ...],
    ) -> VisibleCockpitResultArguments:
        if len(ordered_values) != 1:
            raise ValueError("visible cockpit tool requires exactly one argument")
        return VisibleCockpitResultArguments(ordered_values[0])

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        if not isinstance(arguments, VisibleCockpitResultArguments):
            raise TypeError("visible cockpit tool received the wrong argument type")
        visible = context.stage_context
        as_of = _stage_as_of(visible)
        warnings = _stage_warnings(visible)
        provenance = AgentToolProvenance(
            source="visible-cockpit-result",
            as_of=as_of,
            source_reference=visible.context_reference,
        )
        if arguments.visible_result_reference != visible.context_reference:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="VISIBLE_RESULT_UNAVAILABLE",
                error_message="Requested visible result is not available in this turn",
                provenance=provenance,
                source_reference=visible.context_reference,
            )
        freshness_status = "VISIBLE_RESULT"
        if isinstance(visible, AgentAccumulationContext) and visible.freshness is not None:
            freshness_status = visible.freshness.alignment_state
        result_kind = _RESULT_KIND_BY_STAGE.get(
            visible.stage_kind, visible.stage_kind.value.upper()
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=VisibleCockpitResultData(
                schema_id=self.definition.result_schema_id,
                result_kind=result_kind,
                context=visible,
            ),
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=as_of,
                status=freshness_status,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=visible.context_reference,
        )


def _stage_as_of(context: AgentStageContext) -> date | None:
    value = getattr(context, "as_of", None)
    return value if isinstance(value, date) else None


def _stage_warnings(context: AgentStageContext) -> tuple[str, ...]:
    value = getattr(context, "warnings", ())
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return ()
