"""Single dispatch site for per-stage Research Cockpit context projections (ADR-066)."""

from __future__ import annotations

from typing import Any

from src.application.dto.accumulation_agent import (
    AgentStageContext,
    AgentStageKind,
    AgentTurnRequest,
)
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.agent_accum_screen_context import (
    AgentAccumScreenRawInput,
    build_agent_accum_screen_context,
)
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
    build_agent_accumulation_context,
)

__all__ = [
    "AgentAccumScreenRawInput",
    "AgentContextInvariantError",
    "AgentContextUnavailableError",
    "build_agent_stage_context",
    "build_judge_turn_request",
]


def build_agent_stage_context(
    stage_kind: AgentStageKind,
    raw_stage_input: Any,
) -> AgentStageContext:
    """Build the pure stage projection. Only dispatch site for stage builders.

    Raises
    ------
    AgentContextUnavailableError
        Stage lacks full focused context, or the stage destination is not shipped.
    AgentContextInvariantError
        Identity disagreement inside a stage builder.
    TypeError
        ``raw_stage_input`` is the wrong type for the requested stage.
    """
    if stage_kind is AgentStageKind.ACCUM_JUDGE:
        if not isinstance(raw_stage_input, AccumulationCandidate):
            raise TypeError(
                "accum_judge raw_stage_input must be AccumulationCandidate, "
                f"got {type(raw_stage_input).__name__}"
            )
        return build_agent_accumulation_context(raw_stage_input)

    if stage_kind is AgentStageKind.ACCUM_SCREEN:
        if not isinstance(raw_stage_input, AgentAccumScreenRawInput):
            raise TypeError(
                "accum_screen raw_stage_input must be AgentAccumScreenRawInput, "
                f"got {type(raw_stage_input).__name__}"
            )
        return build_agent_accum_screen_context(raw_stage_input)

    # Remaining destinations land in later slices; refuse honestly rather than fabricate.
    raise AgentContextUnavailableError(
        f"Research Cockpit stage {stage_kind.value!r} context is not available yet"
    )


def build_judge_turn_request(user_text: str, candidate: AccumulationCandidate) -> AgentTurnRequest:
    """Convenience for Judge path callers/tests: build context once into a turn request."""
    return AgentTurnRequest(
        user_text=user_text,
        stage_context=build_agent_stage_context(AgentStageKind.ACCUM_JUDGE, candidate),
    )
