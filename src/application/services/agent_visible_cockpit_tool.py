"""Read-only projection of the exact accumulation result visible this turn."""

from __future__ import annotations

import re
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

_REFERENCE_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_ARGUMENT_SCHEMA_ID = "agent_tool.visible_cockpit.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.visible_cockpit.result.v1"


@dataclass(frozen=True)
class VisibleCockpitResultArguments(AgentToolArguments):
    visible_result_reference: str

    def __post_init__(self) -> None:
        if _REFERENCE_PATTERN.fullmatch(self.visible_result_reference) is None:
            raise ValueError("visible result reference must be canonical sha256")


@dataclass(frozen=True)
class VisibleCockpitResultData:
    schema_id: str
    result_kind: str
    context: AgentAccumulationContext


class VisibleCockpitResultTool:
    """Return only the exact result captured in the invocation context."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        description="Return the exact deterministic accumulation result visible in this turn.",
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
        visible = context.visible_accumulation_context
        provenance = AgentToolProvenance(
            source="visible-cockpit-result",
            as_of=visible.as_of,
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
        freshness_status = (
            visible.freshness.alignment_state if visible.freshness is not None else "VISIBLE_RESULT"
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=VisibleCockpitResultData(
                schema_id=self.definition.result_schema_id,
                result_kind="ACCUMULATION_JUDGE",
                context=visible,
            ),
            warnings=visible.warnings,
            freshness=AgentToolFreshness(
                as_of=visible.as_of,
                status=freshness_status,
                warnings=visible.warnings,
            ),
            provenance=provenance,
            source_reference=visible.context_reference,
        )
