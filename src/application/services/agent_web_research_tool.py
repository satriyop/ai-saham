"""ADR-065 web_research — closed external research tool (confirm + NETWORK_READ)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolApproval,
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolFreshness,
    AgentToolName,
    AgentToolProvenance,
    AgentToolSideEffect,
)

_ARGUMENT_SCHEMA_ID = "agent_tool.web_research.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.web_research.result.v1"
_MAX_QUERY_CHARS = 500
_MAX_RESULTS_CAP = 5


class WebResearchPort(Protocol):
    def research(self, query: str, *, max_results: int) -> tuple["WebResearchSnippet", ...]: ...


@dataclass(frozen=True)
class WebResearchSnippet:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class WebResearchArguments(AgentToolArguments):
    query: str

    def __post_init__(self) -> None:
        q = self.query.strip()
        if not q or len(q) > _MAX_QUERY_CHARS:
            raise ValueError(f"query must be 1-{_MAX_QUERY_CHARS} characters")


@dataclass(frozen=True)
class WebResearchResultData:
    schema_id: str
    query: str
    snippets: tuple[WebResearchSnippet, ...]
    provider: str
    fetched_at: str


class WebResearchTool:
    """Application-owned external research tool; network behind confirm."""

    _definition = AgentToolDefinition(
        name=AgentToolName.WEB_RESEARCH,
        description=(
            "External web research snippets for questions local tools cannot answer. "
            "Requires operator confirm. Not Action authority."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(AgentToolArgumentField("query", "Bounded research query string."),),
        required_context="OPERATOR_CONFIRM_NETWORK",
        timeout_ms=15_000,
        max_result_bytes=32 * 1024,
        side_effect=AgentToolSideEffect.NETWORK_READ,
        approval=AgentToolApproval.PER_CALL,
    )

    def __init__(self, client: WebResearchPort) -> None:
        self._client = client

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> WebResearchArguments:
        if len(ordered_values) != 1:
            raise ValueError("web_research requires exactly one argument: query")
        return WebResearchArguments(ordered_values[0])

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, WebResearchArguments):
            raise TypeError("web_research received the wrong argument type")
        query = arguments.query.strip()
        max_results = 3
        provenance = AgentToolProvenance(
            source="web-research",
            source_reference=f"web_research:{query[:80]}",
        )
        try:
            snippets = self._client.research(query, max_results=max_results)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="WEB_RESEARCH_FAILED",
                error_message="External research failed safely",
                provenance=provenance,
                side_effect=AgentToolSideEffect.NETWORK_READ,
            )
        if not snippets:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="WEB_RESEARCH_EMPTY",
                error_message="External research returned no snippets",
                provenance=provenance,
                side_effect=AgentToolSideEffect.NETWORK_READ,
            )
        clipped = tuple(snippets[:max_results])
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        data = WebResearchResultData(
            schema_id=_RESULT_SCHEMA_ID,
            query=query,
            snippets=clipped,
            provider="deepseek",
            fetched_at=now,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=data,
            warnings=("EXTERNAL_RESEARCH · non-reproducible · not Action authority",),
            freshness=AgentToolFreshness(as_of=date.today(), status="EXTERNAL"),
            provenance=provenance,
            side_effect=AgentToolSideEffect.NETWORK_READ,
        )


class NullWebResearchClient:
    """Offline/default client — never hits the network."""

    def research(self, query: str, *, max_results: int) -> tuple[WebResearchSnippet, ...]:
        del query, max_results
        return ()
