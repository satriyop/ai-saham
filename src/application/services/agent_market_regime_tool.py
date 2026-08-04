"""Bounded agent projection: market-wide regime snapshot (cache-only, cohort-scoped)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

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
from src.domain.value_objects.market_context import MarketContext

_ARGUMENT_SCHEMA_ID = "agent_tool.market_regime.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.market_regime.v1"

_WARN_STALENESS = "MARKET_CONTEXT_STALE"
_WARN_COVERAGE = "MARKET_CONTEXT_COVERAGE"
_WARN_FACTOR = "FACTOR_DATA_UNAVAILABLE"
_WARN_TRANSITION = "REGIME_TRANSITIONING"
_WARN_CODES = frozenset(
    {
        _WARN_STALENESS,
        _WARN_COVERAGE,
        _WARN_FACTOR,
        _WARN_TRANSITION,
    }
)


class _MarketContextReader(Protocol):
    def get(
        self,
        as_of_date: date,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> MarketContext | None: ...

    def get_recent(
        self,
        limit: int = 30,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> list[MarketContext]: ...


@dataclass(frozen=True)
class MarketRegimeArguments(AgentToolArguments):
    as_of: date | None


@dataclass(frozen=True)
class MarketRegimeFactorData:
    name: str
    enabled: bool
    value: float | None
    label: str
    rationale: str


@dataclass(frozen=True)
class MarketRegimeResultData:
    schema_id: str
    as_of: date
    regime: str
    conviction: float
    regime_confidence: float | None
    factors: tuple[MarketRegimeFactorData, ...]
    signal_multiplier: float
    gate_tightening: bool
    regime_stability: str | None
    days_in_regime: int | None
    cohort_id: str
    universe_name: str
    benchmark_ticker: str


class MarketRegimeTool:
    """Project the latest stored MarketContext for the canonical MCE cohort.

    Cache-only: never recomputes via BuildMarketContextUseCase / MarketContextEngine
    and never fetches. Cohort must be injected at composition from the same identity
    derivation production writes use.
    """

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_MARKET_REGIME,
        description=(
            "Return the market-wide regime snapshot from local cache for the "
            "canonical MarketContextEngine cohort: regime (RISK_ON/NEUTRAL/"
            "RISK_OFF/VOLATILE), conviction (0–1 composite), regime_confidence "
            "(boundary-distance; may be null), factor readings (value/label/"
            "rationale, no factor scores), signal_multiplier and gate_tightening "
            "as stored config-derived readings, plus optional stability/days. "
            "Facts only — tape context, not a buy/sell/enter directive."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "as_of",
                "Optional ISO date (YYYY-MM-DD). Empty string defaults to the "
                "latest stored snapshot for the canonical cohort.",
            ),
        ),
        required_context="LOCAL_MARKET_CONTEXT_SNAPSHOT",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(
        self,
        repository: _MarketContextReader,
        *,
        cohort_id: str,
        universe_name: str = "",
        benchmark_ticker: str = "",
        today: Callable[[], date] = date.today,
    ) -> None:
        if not isinstance(cohort_id, str) or not cohort_id.strip():
            raise ValueError("cohort_id must be a non-empty string")
        self._repository = repository
        self._cohort_id = cohort_id
        self._universe_name = universe_name
        self._benchmark_ticker = benchmark_ticker
        self._today = today

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    @property
    def cohort_id(self) -> str:
        return self._cohort_id

    def build_arguments(self, ordered_values: tuple[str, ...]) -> MarketRegimeArguments:
        if len(ordered_values) != 1:
            raise ValueError("market regime tool requires exactly one argument")
        return MarketRegimeArguments(as_of=_parse_as_of(ordered_values[0]))

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, MarketRegimeArguments):
            raise TypeError("market regime tool received the wrong argument type")
        source_reference = f"market-regime:{self._cohort_id}"
        provenance = AgentToolProvenance(
            source="market-context-snapshot",
            source_reference=source_reference,
        )
        requested = arguments.as_of
        if requested is not None and requested > self._today():
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="AS_OF_IN_FUTURE",
                error_message="Requested as_of is in the future; no regime snapshot can exist",
                provenance=provenance,
                source_reference=source_reference,
            )

        try:
            context_snap = self._load_snapshot(requested)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="MARKET_REGIME_READ_FAILED",
                error_message="Market context snapshot could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if context_snap is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="MARKET_REGIME_UNAVAILABLE",
                error_message=(
                    "No stored market context snapshot for the canonical cohort"
                    + (f" on {requested.isoformat()}" if requested is not None else " (latest)")
                ),
                provenance=provenance,
                source_reference=source_reference,
            )

        notes = _collect_warnings(context_snap)
        factors = tuple(
            MarketRegimeFactorData(
                name=f.name,
                enabled=f.enabled,
                value=f.value,
                label=f.label,
                rationale=f.rationale,
            )
            for f in context_snap.factors
        )
        data = MarketRegimeResultData(
            schema_id=_RESULT_SCHEMA_ID,
            as_of=context_snap.as_of_date,
            regime=context_snap.regime.value,
            conviction=context_snap.conviction,
            regime_confidence=context_snap.regime_confidence,
            factors=factors,
            signal_multiplier=context_snap.signal_multiplier,
            gate_tightening=context_snap.gate_tightening,
            regime_stability=context_snap.regime_stability,
            days_in_regime=context_snap.days_in_regime,
            cohort_id=self._cohort_id,
            universe_name=self._universe_name,
            benchmark_ticker=self._benchmark_ticker,
        )
        warnings = tuple(notes)
        has_warn = any(code in _WARN_CODES for code in warnings)
        status = AgentToolExecutionStatus.PARTIAL if has_warn else AgentToolExecutionStatus.SUCCESS
        as_of_ref = context_snap.as_of_date.isoformat()
        source_reference = f"market-regime:{self._cohort_id}:{as_of_ref}"
        provenance = AgentToolProvenance(
            source="market-context-snapshot",
            as_of=context_snap.as_of_date,
            source_reference=source_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=context_snap.as_of_date,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )

    def _load_snapshot(self, requested: date | None) -> MarketContext | None:
        # Always cohort-scoped — never call get()/get_recent() without cohort
        # (multi-cohort dates return false None when unscoped).
        if requested is not None:
            return self._repository.get(
                requested,
                semantic_compatibility_id=self._cohort_id,
            )
        recent = self._repository.get_recent(
            1,
            semantic_compatibility_id=self._cohort_id,
        )
        return recent[0] if recent else None


def _collect_warnings(ctx: MarketContext) -> list[str]:
    notes: list[str] = []
    if ctx.staleness_warning:
        notes.append(_WARN_STALENESS)
    if ctx.coverage_warning:
        notes.append(_WARN_COVERAGE)
    if ctx.transition_warning or ctx.regime_stability == "TRANSITIONING":
        notes.append(_WARN_TRANSITION)
    missing_factor = any(
        f.enabled and (f.value is None or f.label == "UNAVAILABLE") for f in ctx.factors
    )
    if missing_factor:
        notes.append(_WARN_FACTOR)
    return notes


def _parse_as_of(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of must be empty or an ISO date (YYYY-MM-DD)") from exc
