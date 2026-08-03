"""Frozen turn-local inputs available to approved agent read tools."""

from dataclasses import dataclass

from src.application.dto.accumulation_agent import (
    AgentAccumulationContext,
    AgentStageContext,
)


@dataclass(frozen=True)
class AgentToolExecutionContext:
    """Exact deterministic result captured for the current agent turn (ADR-066)."""

    stage_context: AgentStageContext

    @property
    def visible_accumulation_context(self) -> AgentAccumulationContext:
        """Judge-only accessor for tools that still assume accumulation context.

        Prefer ``stage_context`` for new code. Raises TypeError when the active
        stage is not the accumulation Judge.
        """
        ctx = self.stage_context
        if not isinstance(ctx, AgentAccumulationContext):
            raise TypeError(
                "visible_accumulation_context requires accum_judge stage_context, "
                f"got {ctx.stage_kind.value}"
            )
        return ctx
