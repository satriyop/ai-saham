"""Bounded agent projection: composed ticker research brief (facts only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Protocol

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
from src.application.use_case.build_ticker_research_brief_use_case import (
    BuildTickerResearchBriefRequest,
    TickerResearchBriefResult,
    parse_sections_csv,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_research_brief.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_research_brief.v1"


class _BriefUseCase(Protocol):
    def execute(self, request: BuildTickerResearchBriefRequest) -> TickerResearchBriefResult: ...


@dataclass(frozen=True)
class TickerResearchBriefArguments(AgentToolArguments):
    ticker: str
    as_of: date | None
    sections: tuple[str, ...]

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")


@dataclass(frozen=True)
class TickerResearchBriefResultData:
    """Agent payload: mirrors the shared use-case result (no minted verdict)."""

    schema_id: str
    ticker: str
    as_of: date | None
    sections_requested: tuple[str, ...]
    overall_status: str
    warnings: tuple[str, ...]
    section_meta: tuple[object, ...]
    judge: object | None
    broker_flow: object | None
    foreign_flow: object | None
    ownership: object | None
    corporate_actions: object | None
    regime: object | None


class TickerResearchBriefTool:
    """Project BuildTickerResearchBriefUseCase into the agent tool registry."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_RESEARCH_BRIEF,
        description=(
            "Return one PIT-aligned research brief for a ticker: deterministic "
            "Judge Action + key accum facts, broker tops/bandar summary, foreign "
            "net trend, ownership composition, upcoming corporate actions, and "
            "market regime snapshot. Each section is independently statused. "
            "Facts only — surfaces the engine Action; does not mint a brief "
            "verdict or composite recommendation."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "as_of",
                "Optional ISO date (YYYY-MM-DD) for PIT alignment on sections "
                "that support it. Empty string defaults to latest per section.",
            ),
            AgentToolArgumentField(
                "sections",
                "Optional comma-separated subset: judge,broker_flow,foreign_flow,"
                "ownership,corporate_actions,regime. Empty = all default sections.",
            ),
        ),
        required_context="LOCAL_TICKER_RESEARCH_CACHE",
        timeout_ms=12_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, use_case: _BriefUseCase) -> None:
        self._use_case = use_case

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerResearchBriefArguments:
        if len(ordered_values) != 3:
            raise ValueError("ticker research brief tool requires exactly three arguments")
        ticker = ordered_values[0].strip().upper()
        as_of = _parse_as_of(ordered_values[1])
        sections = parse_sections_csv(ordered_values[2])
        return TickerResearchBriefArguments(ticker=ticker, as_of=as_of, sections=sections)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerResearchBriefArguments):
            raise TypeError("ticker research brief tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-research-brief:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-research-brief",
            source_reference=source_reference,
        )
        try:
            brief = self._use_case.execute(
                BuildTickerResearchBriefRequest(
                    ticker=ticker,
                    as_of=arguments.as_of,
                    sections=arguments.sections,
                )
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_RESEARCH_BRIEF_FAILED",
                error_message="Ticker research brief could not be assembled",
                provenance=provenance,
                source_reference=source_reference,
            )

        data = TickerResearchBriefResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=brief.ticker,
            as_of=brief.as_of,
            sections_requested=brief.sections_requested,
            overall_status=brief.overall_status,
            warnings=brief.warnings,
            section_meta=brief.section_meta,
            judge=brief.judge,
            broker_flow=brief.broker_flow,
            foreign_flow=brief.foreign_flow,
            ownership=brief.ownership,
            corporate_actions=brief.corporate_actions,
            regime=brief.regime,
        )
        status = _map_status(brief.overall_status)
        # PARTIAL requires non-empty warnings under the agent result contract.
        warnings = brief.warnings
        if status is AgentToolExecutionStatus.PARTIAL and not warnings:
            warnings = ("BRIEF_PARTIAL",)
        if status is AgentToolExecutionStatus.UNAVAILABLE:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=status,
                data=None,
                error_code="TICKER_RESEARCH_BRIEF_UNAVAILABLE",
                error_message="No brief sections could be assembled for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )
        source_reference = (
            f"ticker-research-brief:{ticker}:{brief.as_of.isoformat() if brief.as_of else 'none'}"
        )
        provenance = AgentToolProvenance(
            source="ticker-research-brief",
            as_of=brief.as_of,
            source_reference=source_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=warnings if status is AgentToolExecutionStatus.PARTIAL else brief.warnings,
            freshness=AgentToolFreshness(
                as_of=brief.as_of,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _map_status(overall: str) -> AgentToolExecutionStatus:
    if overall == "SUCCESS":
        return AgentToolExecutionStatus.SUCCESS
    if overall == "PARTIAL":
        return AgentToolExecutionStatus.PARTIAL
    if overall == "FAILED":
        return AgentToolExecutionStatus.FAILED
    return AgentToolExecutionStatus.UNAVAILABLE


def _parse_as_of(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of must be empty or an ISO date (YYYY-MM-DD)") from exc
