"""Frozen turn-local inputs available to approved agent read tools."""

from dataclasses import dataclass

from src.application.dto.accumulation_agent import AgentAccumulationContext


@dataclass(frozen=True)
class AgentToolExecutionContext:
    """Exact deterministic result captured for the current agent turn."""

    visible_accumulation_context: AgentAccumulationContext
