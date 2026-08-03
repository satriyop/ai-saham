"""Bounded agent projection: ticker ownership composition / float (cache-only)."""

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
from src.domain.value_objects.shareholding_composition import ShareholdingComposition

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_ownership.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_ownership.v1"

_WARN_TOP_HOLDER_UNAVAILABLE = "TOP_HOLDER_UNAVAILABLE"
_WARN_TOTAL_SHARES_UNAVAILABLE = "TOTAL_SHARES_UNAVAILABLE"
_WARN_REPORT_DATE_UNAVAILABLE = "REPORT_DATE_UNAVAILABLE"
_WARN_CODES = frozenset(
    {
        _WARN_TOP_HOLDER_UNAVAILABLE,
        _WARN_TOTAL_SHARES_UNAVAILABLE,
        _WARN_REPORT_DATE_UNAVAILABLE,
    }
)


class _OwnershipCacheSource(Protocol):
    def get_ownership(self, ticker: str) -> object | None: ...


@dataclass(frozen=True)
class TickerOwnershipArguments(AgentToolArguments):
    ticker: str

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")


@dataclass(frozen=True)
class TickerOwnershipResultData:
    schema_id: str
    ticker: str
    report_date: date | None
    institution_pct: float
    individual_pct: float
    top_holder_name: str
    top_holder_pct: float
    total_shares: int | None
    total_shares_formatted: str | None


class TickerOwnershipTool:
    """Project the existing cache-only shareholding composition for one ticker."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_OWNERSHIP,
        description=(
            "Return one ticker's cached ownership composition: institution vs "
            "individual percentages, named top holder, and total shares. "
            "Facts only — not a float-tightness score."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
        ),
        required_context="LOCAL_TICKER_OWNERSHIP_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, ownership_source: _OwnershipCacheSource) -> None:
        self._ownership_source = ownership_source

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerOwnershipArguments:
        if len(ordered_values) != 1:
            raise ValueError("ticker ownership tool requires exactly one argument")
        return TickerOwnershipArguments(ordered_values[0].strip().upper())

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerOwnershipArguments):
            raise TypeError("ticker ownership tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-ownership:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-ownership-cache",
            source_reference=source_reference,
        )
        try:
            composition = self._ownership_source.get_ownership(ticker)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_OWNERSHIP_READ_FAILED",
                error_message="Ticker ownership cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if not isinstance(composition, ShareholdingComposition):
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_OWNERSHIP_UNAVAILABLE",
                error_message="No cached ownership composition is available for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )

        notes: list[str] = []
        if not composition.top_holder_name.strip():
            notes.append(_WARN_TOP_HOLDER_UNAVAILABLE)
        if composition.total_shares is None:
            notes.append(_WARN_TOTAL_SHARES_UNAVAILABLE)
        if composition.report_date is None:
            notes.append(_WARN_REPORT_DATE_UNAVAILABLE)

        data = TickerOwnershipResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=ticker,
            report_date=composition.report_date,
            institution_pct=composition.institution_pct,
            individual_pct=composition.individual_pct,
            top_holder_name=composition.top_holder_name,
            top_holder_pct=composition.top_holder_pct,
            total_shares=composition.total_shares,
            total_shares_formatted=composition.total_shares_formatted,
        )
        warnings = tuple(notes)
        has_warn = any(code in _WARN_CODES for code in warnings)
        status = AgentToolExecutionStatus.PARTIAL if has_warn else AgentToolExecutionStatus.SUCCESS
        as_of_ref = composition.report_date.isoformat() if composition.report_date else "none"
        source_reference = f"ticker-ownership:{ticker}:{as_of_ref}"
        provenance = AgentToolProvenance(
            source="ticker-ownership-cache",
            as_of=composition.report_date,
            source_reference=source_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=composition.report_date,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )
