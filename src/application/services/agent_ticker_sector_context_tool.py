"""Bounded agent tool: descriptive L2a+L2b sector context for one ticker."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

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
from src.application.use_case.build_ticker_sector_context_use_case import (
    BuildTickerSectorContextRequest,
    BuildTickerSectorContextUseCase,
    SectorMacroContextFacts,
    SectorPeerContextFacts,
    TickerSectorContextResult,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_sector_context.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_sector_context.v1"
_DEFAULT_PEERS = 10
_MAX_PEERS = 10

_WARN_CODES = frozenset(
    {
        "SECTOR_PEER_CONTEXT_UNAVAILABLE",
        "SECTOR_MACRO_CONTEXT_UNAVAILABLE",
        "SECTOR_PEERS_THIN",
    }
)


@dataclass(frozen=True)
class TickerSectorContextArguments(AgentToolArguments):
    ticker: str
    as_of: date | None
    peers_limit: int

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.peers_limit < 1 or self.peers_limit > _MAX_PEERS:
            raise ValueError(f"peers_limit must be between 1 and {_MAX_PEERS}")


@dataclass(frozen=True)
class SectorPeerContextData:
    sector_label: str | None
    peer_count: int
    peer_tickers: tuple[str, ...]
    sector_20d_return: float | None
    sector_vs_ihsg_20d: float | None
    sector_breadth: float | None
    ticker_vs_sector_rs: float | None
    sector_regime: str


@dataclass(frozen=True)
class SectorMacroFactorData:
    name: str
    series: str
    value: float | None
    label: str
    rationale: str


@dataclass(frozen=True)
class SectorMacroContextData:
    sector_group: str | None
    macro_regime: str
    factors: tuple[SectorMacroFactorData, ...]


@dataclass(frozen=True)
class TickerSectorContextResultData:
    schema_id: str
    ticker: str
    as_of: date
    sector_group: str | None
    peer_context: SectorPeerContextData | None
    macro_context: SectorMacroContextData | None


class TickerSectorContextTool:
    """Project BuildTickerSectorContextUseCase for the closed agent registry."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_SECTOR_CONTEXT,
        description=(
            "Return descriptive sector context for one ticker: peer-relative "
            "sector strength (20d return, vs IHSG, breadth, ticker RS, regime label) "
            "and routed sector-macro factor readings (value/label/rationale only). "
            "Facts only — not a sector buy/avoid verdict or composite score."
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
                "Optional ISO session date (YYYY-MM-DD). Empty = latest candle date.",
            ),
            AgentToolArgumentField(
                "peers_limit",
                "Optional max peer tickers (1-10). Empty defaults to 10.",
            ),
        ),
        required_context="LOCAL_SECTOR_CONTEXT_CACHE",
        timeout_ms=5_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, use_case: BuildTickerSectorContextUseCase) -> None:
        self._use_case = use_case

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerSectorContextArguments:
        if len(ordered_values) != 3:
            raise ValueError("ticker sector context tool requires exactly three arguments")
        ticker = ordered_values[0].strip().upper()
        as_of = _parse_optional_date(ordered_values[1])
        peers = _parse_peers(ordered_values[2])
        return TickerSectorContextArguments(ticker=ticker, as_of=as_of, peers_limit=peers)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerSectorContextArguments):
            raise TypeError("ticker sector context tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-sector-context:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-sector-context-cache",
            source_reference=source_reference,
        )
        try:
            result = self._use_case.execute(
                BuildTickerSectorContextRequest(
                    ticker=ticker,
                    as_of=arguments.as_of,
                    peers_limit=arguments.peers_limit,
                )
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_SECTOR_CONTEXT_READ_FAILED",
                error_message="Sector context cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if result is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_SECTOR_CONTEXT_UNAVAILABLE",
                error_message="No sector peer or macro context is available for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )

        data = _project(result)
        warnings = result.warnings
        has_warn = any(w in _WARN_CODES for w in warnings) or (
            result.peer_context is None or result.macro_context is None
        )
        # Ensure PARTIAL when one dimension missing even if warning list incomplete
        if result.peer_context is None and "SECTOR_PEER_CONTEXT_UNAVAILABLE" not in warnings:
            warnings = warnings + ("SECTOR_PEER_CONTEXT_UNAVAILABLE",)
            has_warn = True
        if result.macro_context is None and "SECTOR_MACRO_CONTEXT_UNAVAILABLE" not in warnings:
            warnings = warnings + ("SECTOR_MACRO_CONTEXT_UNAVAILABLE",)
            has_warn = True
        status = AgentToolExecutionStatus.PARTIAL if has_warn else AgentToolExecutionStatus.SUCCESS
        source_reference = f"ticker-sector-context:{ticker}:{result.as_of.isoformat()}"
        provenance = AgentToolProvenance(
            source="ticker-sector-context-cache",
            as_of=result.as_of,
            source_reference=source_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=tuple(dict.fromkeys(warnings)),
            freshness=AgentToolFreshness(
                as_of=result.as_of,
                status=status.value,
                warnings=tuple(dict.fromkeys(warnings)),
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _project(result: TickerSectorContextResult) -> TickerSectorContextResultData:
    return TickerSectorContextResultData(
        schema_id=_RESULT_SCHEMA_ID,
        ticker=result.ticker,
        as_of=result.as_of,
        sector_group=result.sector_group,
        peer_context=_peer(result.peer_context),
        macro_context=_macro(result.macro_context),
    )


def _peer(p: SectorPeerContextFacts | None) -> SectorPeerContextData | None:
    if p is None:
        return None
    return SectorPeerContextData(
        sector_label=p.sector_label,
        peer_count=p.peer_count,
        peer_tickers=p.peer_tickers,
        sector_20d_return=p.sector_20d_return,
        sector_vs_ihsg_20d=p.sector_vs_ihsg_20d,
        sector_breadth=p.sector_breadth,
        ticker_vs_sector_rs=p.ticker_vs_sector_rs,
        sector_regime=p.sector_regime,
    )


def _macro(m: SectorMacroContextFacts | None) -> SectorMacroContextData | None:
    if m is None:
        return None
    return SectorMacroContextData(
        sector_group=m.sector_group,
        macro_regime=m.macro_regime,
        factors=tuple(
            SectorMacroFactorData(
                name=f.name,
                series=f.series,
                value=f.value,
                label=f.label,
                rationale=f.rationale,
            )
            for f in m.factors
        ),
    )


def _parse_optional_date(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of must be empty or an ISO date YYYY-MM-DD") from exc


def _parse_peers(raw: str) -> int:
    text = raw.strip()
    if not text:
        return _DEFAULT_PEERS
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("peers_limit must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"peers_limit must be between 1 and {_MAX_PEERS}")
    return min(value, _MAX_PEERS)
