"""Single dispatch site for per-stage Research Cockpit context projections (ADR-066)."""

from __future__ import annotations

from typing import Any

from src.application.dto.accumulation_agent import (
    AgentStageContext,
    AgentStageKind,
    AgentTurnRequest,
)
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.ticker_dashboard import TickerDashboard
from src.application.services.agent_accum_screen_context import (
    AgentAccumScreenRawInput,
    build_agent_accum_screen_context,
)
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
    build_agent_accumulation_context,
)
from src.application.services.agent_broker_desk_tool import BrokerDeskResultData
from src.application.services.agent_view_broker_context import (
    build_agent_view_broker_context,
    build_agent_view_broker_context_from_result,
)
from src.application.services.agent_view_ticker_context import build_agent_view_ticker_context

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

    if stage_kind is AgentStageKind.VIEW_TICKER:
        if not isinstance(raw_stage_input, TickerDashboard):
            raise TypeError(
                "view_ticker raw_stage_input must be TickerDashboard, "
                f"got {type(raw_stage_input).__name__}"
            )
        return build_agent_view_ticker_context(raw_stage_input)

    if stage_kind is AgentStageKind.VIEW_BROKER:
        # Accept either pre-projected BrokerDeskResultData or (page, use_case_result).
        if isinstance(raw_stage_input, BrokerDeskResultData):
            return build_agent_view_broker_context(raw_stage_input)
        if (
            isinstance(raw_stage_input, tuple)
            and len(raw_stage_input) == 2
            and isinstance(raw_stage_input[0], str)
        ):
            page, result = raw_stage_input
            return build_agent_view_broker_context_from_result(page, result)
        raise TypeError(
            "view_broker raw_stage_input must be BrokerDeskResultData or "
            f"(page, desk_result), got {type(raw_stage_input).__name__}"
        )

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
