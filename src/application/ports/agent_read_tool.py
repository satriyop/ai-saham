"""Application boundary for independently approved read-only agent tools."""

from typing import Protocol

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
)


class AgentReadToolPort(Protocol):
    @property
    def definition(self) -> AgentToolDefinition: ...

    def build_arguments(self, ordered_values: tuple[str, ...]) -> AgentToolArguments: ...

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult: ...
