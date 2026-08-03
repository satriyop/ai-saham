"""Bounded agent projection: ticker ownership period history (cache-only)."""

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
from src.application.use_case.view_ticker_ownership_history_use_case import (
    MAX_LIMIT,
    ViewTickerOwnershipHistoryRequest,
    ViewTickerOwnershipHistoryResult,
)
from src.domain.value_objects.shareholding_composition import ShareholdingComposition

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_ownership_history.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_ownership_history.v1"
_DEFAULT_LIMIT = MAX_LIMIT

_INFO_SINGLE_PERIOD_ONLY = "SINGLE_PERIOD_ONLY"


class _OwnershipHistoryUseCase(Protocol):
    def execute(
        self, request: ViewTickerOwnershipHistoryRequest
    ) -> ViewTickerOwnershipHistoryResult | None: ...


@dataclass(frozen=True)
class TickerOwnershipHistoryArguments(AgentToolArguments):
    ticker: str
    limit: int

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.limit < 1 or self.limit > MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")


@dataclass(frozen=True)
class TickerOwnershipHistoryPeriodData:
    report_date: date | None
    institution_pct: float
    individual_pct: float
    free_float_pct: float
    top_holder_name: str
    top_holder_pct: float
    total_shares: int | None
    total_shares_formatted: str | None


@dataclass(frozen=True)
class TickerOwnershipHistoryResultData:
    schema_id: str
    ticker: str
    as_of: date | None
    period_count: int
    periods: tuple[TickerOwnershipHistoryPeriodData, ...]
    institution_pct_change: float | None
    float_change: float | None
    top_holder_pct_change: float | None


class TickerOwnershipHistoryTool:
    """Compose cache-only ownership period history into a bounded trend projection."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_OWNERSHIP_HISTORY,
        description=(
            "Return one ticker's ownership composition over its last cached filing "
            "periods (deduplicated re-fetches) with latest-period-over-previous "
            "deltas for institution %, free float %, and top holder %. "
            "Facts only — not a float-tightness score."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "limit",
                f"Optional number of periods (1-{MAX_LIMIT}). Empty string defaults "
                f"to {_DEFAULT_LIMIT}; values above {MAX_LIMIT} are capped.",
            ),
        ),
        required_context="LOCAL_TICKER_OWNERSHIP_HISTORY_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, use_case: _OwnershipHistoryUseCase) -> None:
        self._use_case = use_case

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerOwnershipHistoryArguments:
        if len(ordered_values) != 2:
            raise ValueError("ticker ownership history tool requires exactly two arguments")
        ticker = ordered_values[0].strip().upper()
        limit = _parse_limit(ordered_values[1])
        return TickerOwnershipHistoryArguments(ticker=ticker, limit=limit)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerOwnershipHistoryArguments):
            raise TypeError("ticker ownership history tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-ownership-history:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-ownership-history-cache",
            source_reference=source_reference,
        )
        try:
            result = self._use_case.execute(
                ViewTickerOwnershipHistoryRequest(ticker=ticker, limit=arguments.limit)
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_OWNERSHIP_HISTORY_READ_FAILED",
                error_message="Ticker ownership history cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if result is None or not result.periods:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_OWNERSHIP_HISTORY_UNAVAILABLE",
                error_message="No cached ownership periods are available for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )

        periods = tuple(_period_row(p) for p in result.periods)
        notes: list[str] = []
        if len(periods) < 2:
            notes.append(_INFO_SINGLE_PERIOD_ONLY)

        data = TickerOwnershipHistoryResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=result.ticker,
            as_of=result.as_of,
            period_count=len(periods),
            periods=periods,
            institution_pct_change=result.institution_pct_change,
            float_change=result.float_change,
            top_holder_pct_change=result.top_holder_pct_change,
        )
        warnings = tuple(notes)
        as_of_ref = result.as_of.isoformat() if result.as_of else "none"
        source_reference = f"ticker-ownership-history:{ticker}:{as_of_ref}"
        provenance = AgentToolProvenance(
            source="ticker-ownership-history-cache",
            as_of=result.as_of,
            source_reference=source_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=result.as_of,
                status=AgentToolExecutionStatus.SUCCESS.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _period_row(composition: ShareholdingComposition) -> TickerOwnershipHistoryPeriodData:
    return TickerOwnershipHistoryPeriodData(
        report_date=composition.report_date,
        institution_pct=composition.institution_pct,
        individual_pct=composition.individual_pct,
        free_float_pct=composition.free_float_pct,
        top_holder_name=composition.top_holder_name,
        top_holder_pct=composition.top_holder_pct,
        total_shares=composition.total_shares,
        total_shares_formatted=composition.total_shares_formatted,
    )


def _parse_limit(raw: str) -> int:
    text = raw.strip()
    if not text:
        return _DEFAULT_LIMIT
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("limit must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    return min(value, MAX_LIMIT)
