"""Channel-neutral DTOs for one read-only Research Cockpit commentary turn."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from src.application.dto.agent_session import AgentSessionPack
from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentModelToolChoice,
    AgentToolDefinition,
    AgentToolExecutionResult,
)


class AgentTurnStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentModelResponseKind(str, Enum):
    ANSWER = "ANSWER"
    TOOL_CALLS = "TOOL_CALLS"


class AgentModelUnavailableReason(str, Enum):
    DISABLED = "DISABLED"
    UNSUPPORTED_PROVIDER = "UNSUPPORTED_PROVIDER"
    MISSING_CREDENTIAL = "MISSING_CREDENTIAL"


class AgentStageKind(str, Enum):
    """Named AI Research Cockpit destination stages (ADR-066)."""

    ACCUM_JUDGE = "accum_judge"
    ACCUM_SCREEN = "accum_screen"
    VIEW_TICKER = "view_ticker"
    VIEW_BROKER = "view_broker"
    PREOPEN_SCREEN = "preopen_screen"
    PLAN_SWING = "plan_swing"


@dataclass(frozen=True)
class AgentStageContext:
    """Common frozen base for per-stage pure projections (ADR-066).

    Discriminated by ``stage_kind`` (property on members) + ``schema_id``.
    ``stage_kind`` is not a dataclass field so content hashes stay bit-stable
    when existing member schemas gain the discriminator API.
    """

    schema_id: str
    context_reference: str

    @property
    def stage_kind(self) -> AgentStageKind:
        raise NotImplementedError

    @property
    def session_subject(self) -> str:
        """Stable process-session anchor (ticker or stage-scoped subject)."""
        raise NotImplementedError

    def canonical_payload(self) -> dict[str, Any]:
        return _json_value(self, exclude_context_reference=True)


@dataclass(frozen=True)
class AgentTurnRequest:
    """One cockpit turn carrying the already-built stage projection (ADR-066 D1)."""

    user_text: str
    stage_context: AgentStageContext


@dataclass(frozen=True)
class AgentTradeSetupFacts:
    snapshot_date: date
    action: str
    signal_score: int
    signal_score_raw: int
    signal_strength: str
    blocking_gates: tuple[str, ...]
    regime: str | None
    signal_multiplier: float
    gate_tightening: bool
    rationale: str


@dataclass(frozen=True)
class AgentDecisionConstraintsFacts:
    max_decision: str
    regime: str | None
    regime_enter_allowed: bool
    regime_size_multiplier: float
    setup_family: str | None
    setup_regime_action: str | None
    effective_size_multiplier: float
    constraint_reasons: tuple[str, ...]


@dataclass(frozen=True)
class AgentSignalFacts:
    identity_purpose: str
    policy_contract: str
    ticker: str
    snapshot_date: date
    score: int
    strength: str
    entry_quality: str
    breakdown: tuple[tuple[str, float], ...]
    rationale: tuple[str, ...]
    authority_coverage: float | None
    coverage_warning: str | None
    decision_constraints: AgentDecisionConstraintsFacts | None
    availability_enforcement: str | None


@dataclass(frozen=True)
class AgentRiskFacts:
    snapshot_date: date
    verdict: str
    gate_triggered: str | None
    gate_is_structural: bool | None
    gate_confidence: int | None
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class AgentAccumulationComponentFacts:
    key: str
    score_points: float | None
    max_points: float
    status: str


@dataclass(frozen=True)
class AgentAccumulationFacts:
    ticker: str
    snapshot_date: date
    accum_score: float
    max_score: float
    component_coverage: float
    missing_components: tuple[str, ...]
    components: tuple[AgentAccumulationComponentFacts, ...]
    net_buy_ratio: float
    consecutive_streak: int
    vwap_discount_pct: float | None
    rsi: float | None
    avg_flow_ratio: float | None
    bb_width_pctile: float | None
    bci_label: str | None
    bci_tier1_count: int


@dataclass(frozen=True)
class AgentDecisionRationale:
    trade_setup: str
    signal: tuple[str, ...]
    risk: tuple[str, ...]
    decision_constraints: tuple[str, ...]
    coverage_warning: str | None


@dataclass(frozen=True)
class AgentSetupReadinessFacts:
    setup_family: str
    status: str
    current_phase: str | None
    missing_required_inputs: tuple[str, ...]
    failed_requirements: tuple[str, ...]


@dataclass(frozen=True)
class AgentSetupPhaseFacts:
    current_phase: str
    previous_phase: str | None
    phase_age_sessions: int
    detection_strength: float
    input_coverage: float
    sequence_valid: bool | None
    reasons: tuple[str, ...]
    unavailable_evidence_reasons: tuple[str, ...]
    volume_dry_up_ratio: float | None
    volume_expansion_ratio: float | None
    volume_dry_up_confirmed: bool | None
    volume_expansion_confirmed: bool | None
    volume_trigger_confirmed: bool | None


@dataclass(frozen=True)
class AgentFreshnessFacts:
    candle_as_of: date | None
    broker_as_of: date | None
    expected_latest_eod: date | None
    candle_state: str
    broker_state: str
    alignment_state: str
    sources_aligned: bool
    signal_evidence_coverage: float | None


@dataclass(frozen=True)
class AgentSourceAssessmentFacts:
    source_family: str
    decision_at: datetime
    observed_through: date | None
    available_at: datetime | None
    expected_available_at: datetime | None
    status: str
    is_authoritative: bool
    reason: str | None
    notes: tuple[str, ...]


@dataclass(frozen=True)
class AgentSourceAvailabilityFacts:
    evidence_group: str
    all_authoritative: bool
    settled_authority_fraction: float
    unassessed_contributors: tuple[str, ...]
    assessments: tuple[AgentSourceAssessmentFacts, ...]


@dataclass(frozen=True)
class AgentSourceDates:
    latest_candle_date: date | None
    latest_broker_date: date | None
    latest_broker_daily_flow_date: date | None


@dataclass(frozen=True)
class AgentAccumulationContext(AgentStageContext):
    """Judge-stage projection member (`stage_kind=accum_judge`, schema tui_agent.accum_judge.v1)."""

    ticker: str
    as_of: date
    trade_setup: AgentTradeSetupFacts
    signal: AgentSignalFacts
    risk: AgentRiskFacts | None
    accumulation: AgentAccumulationFacts
    rationale: AgentDecisionRationale
    setup_readiness: AgentSetupReadinessFacts | None
    setup_phase_diagnostic: AgentSetupPhaseFacts | None
    freshness: AgentFreshnessFacts | None
    source_availability: tuple[AgentSourceAvailabilityFacts, ...]
    source_dates: AgentSourceDates
    warnings: tuple[str, ...]
    # Screen-window top broker codes for this ticker (local cache; may be empty).
    top_brokers: tuple[str, ...] = ()
    institutional_flag: bool | None = None

    @property
    def stage_kind(self) -> AgentStageKind:
        return AgentStageKind.ACCUM_JUDGE

    @property
    def session_subject(self) -> str:
        return self.ticker


@dataclass(frozen=True)
class AgentAccumScreenCandidateSummary:
    """Bounded board-row facts for cohort stages (not a full Judge projection)."""

    rank: int
    ticker: str
    as_of: date
    signal_score: int | None
    accum_score: float | None
    action: str | None
    phase: str | None
    streak: int | None
    gate: str | None
    net_buy_ratio: float | None


@dataclass(frozen=True)
class AgentAccumScreenContext(AgentStageContext):
    """Accumulation screen board cohort (`stage_kind=accum_screen`, tui_agent.accum_screen.v1)."""

    as_of: date
    screen_kind: str
    universe: str
    window_days: int
    sort_by: str
    top_limit: int | None
    regime: str | None
    filter_policy: tuple[tuple[str, str | int | float | bool | None], ...]
    cohort_total: int
    shown: int
    members: tuple[AgentAccumScreenCandidateSummary, ...]
    cohort_identity: str
    warnings: tuple[str, ...] = ()

    @property
    def stage_kind(self) -> AgentStageKind:
        return AgentStageKind.ACCUM_SCREEN

    @property
    def session_subject(self) -> str:
        return f"ACCUM_SCREEN:{self.as_of.isoformat()}"


@dataclass(frozen=True)
class AgentPreOpenCandidateSummary:
    """Bounded pre-open board-row facts (not a full Judge projection)."""

    rank: int
    ticker: str
    as_of: date
    action: str | None
    iep: float | None
    iep_gap_pct: float | None
    iev: float | None
    ncp: str | None
    delta_iev: float | None
    risk: str | None


@dataclass(frozen=True)
class AgentPreOpenScreenContext(AgentStageContext):
    """Pre-open screen board cohort (`stage_kind=preopen_screen`, tui_agent.preopen_screen.v1)."""

    as_of: date
    screen_kind: str
    capture_phase: str | None
    ncp_authoritative: bool | None
    source_is_live: bool | None
    session_source: str | None
    session_phase: str | None
    regime: str | None
    total_movers_seen: int | None
    filter_policy: tuple[tuple[str, str | int | float | bool | None], ...]
    cohort_total: int
    shown: int
    members: tuple[AgentPreOpenCandidateSummary, ...]
    cohort_identity: str
    warnings: tuple[str, ...] = ()

    @property
    def stage_kind(self) -> AgentStageKind:
        return AgentStageKind.PREOPEN_SCREEN

    @property
    def session_subject(self) -> str:
        return f"PREOPEN_SCREEN:{self.as_of.isoformat()}"


@dataclass(frozen=True)
class AgentViewTickerContext(AgentStageContext):
    """View-ticker cache dashboard (`stage_kind=view_ticker`, tui_agent.view_ticker.v1).

    Field shapes reuse the closed tool projection (price/flow/fundamentals, …)
    so stage context and get_ticker_dashboard stay aligned.
    """

    ticker: str
    as_of: date | None
    today: date
    mode: str
    # Nested projection is a plain mapping-friendly frozen object graph built by
    # project_ticker_dashboard_for_agent (typed as Any to avoid a circular import
    # between dto and services; runtime type is TickerDashboardResultData fields).
    freshness: tuple[Any, ...]
    identity: Any | None
    price: Any | None
    fundamentals: Any | None
    forward_estimates: Any | None
    analyst: Any | None
    earnings: tuple[Any, ...]
    ownership: Any | None
    bandar: Any | None
    foreign_flow: Any | None
    corporate_action_count: int
    corporate_action_status: str
    insider_transaction_count: int
    insider_status: str
    insider_last_known: date | None
    iev_row_count: int
    sentiment_log_count: int
    profile_available: bool
    seasonality_available: bool
    sector_macro_diagnostic_available: bool
    missing_branches: tuple[str, ...]
    stale_branches: tuple[str, ...]
    error_branches: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def stage_kind(self) -> AgentStageKind:
        return AgentStageKind.VIEW_TICKER

    @property
    def session_subject(self) -> str:
        return self.ticker.upper()


@dataclass(frozen=True)
class AgentViewBrokerContext(AgentStageContext):
    """View-broker desk (`stage_kind=view_broker`, tui_agent.view_broker.v1).

    Nested desk payload reuses BrokerDeskResultData field shapes from the closed
    get_broker_desk tool so stage context and tools stay aligned.
    """

    broker_code: str
    broker_name: str
    broker_type: str
    view: str
    as_of: date | None
    scope_note: str
    show: Any | None
    top_stocks: Any | None
    top_matrix: Any | None
    flow: Any | None
    calendar: Any | None
    history: Any | None
    warnings: tuple[str, ...] = ()

    @property
    def stage_kind(self) -> AgentStageKind:
        return AgentStageKind.VIEW_BROKER

    @property
    def session_subject(self) -> str:
        return f"BROKER:{self.broker_code}:{self.view}"


@dataclass(frozen=True)
class AgentModelRequest:
    system_policy: str
    user_text: str
    context: AgentStageContext
    max_output_tokens: int
    tool_definitions: tuple[AgentToolDefinition, ...] = ()
    tool_choice: AgentModelToolChoice = AgentModelToolChoice.NONE
    prior_tool_calls: tuple[AgentModelToolCall, ...] = ()
    tool_results: tuple[AgentToolExecutionResult, ...] = ()
    session_pack: AgentSessionPack | None = None

    def __post_init__(self) -> None:
        if self.max_output_tokens <= 0:
            raise ValueError("agent model output limit must be positive")
        has_prior = bool(self.prior_tool_calls or self.tool_results)
        if has_prior:
            if not self.tool_definitions or len(self.prior_tool_calls) != len(self.tool_results):
                raise ValueError("tool history requires matched calls, results, and definitions")
            if tuple(call.call_id for call in self.prior_tool_calls) != tuple(
                result.call_id for result in self.tool_results
            ):
                raise ValueError("tool history call/result identities must match")
        if self.tool_choice is AgentModelToolChoice.AUTO:
            if not self.tool_definitions:
                raise ValueError("auto tool choice requires registered definitions")
            # Initial auto: no prior. Multi-round continue: matched prior history.
        elif self.tool_choice is AgentModelToolChoice.NONE:
            # Final answer call: definitions optional; prior history when tools ran.
            pass
        elif self.tool_definitions:
            raise ValueError("tool definitions without auto choice or prior results are invalid")


@dataclass(frozen=True)
class AgentModelResponse:
    text: str
    provider: str
    model: str
    response_id: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    kind: AgentModelResponseKind = AgentModelResponseKind.ANSWER
    tool_calls: tuple[AgentModelToolCall, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("agent model response requires provider and model")
        if self.kind is AgentModelResponseKind.ANSWER:
            if not self.text.strip() or self.tool_calls:
                raise ValueError("agent answer requires text and no tool calls")
        elif self.text or not 1 <= len(self.tool_calls) <= 2:
            raise ValueError("agent tool response requires one or two calls and no answer")


@dataclass(frozen=True)
class AgentTurnResult:
    status: AgentTurnStatus
    answer: str = ""
    context_reference: str | None = None
    provider: str | None = None
    model: str | None = None
    response_id: str | None = None
    warnings: tuple[str, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_message: str | None = None
    tool_results: tuple[AgentToolExecutionResult, ...] = ()
    session_id: str | None = None
    turn_sequence: int | None = None
    # ADR-065: structured tool-gap clues (also mirrored into warnings operator lines)
    gap_clues: tuple = ()
    # True when this turn executed or denied an elevated/external tool after approve path
    elevated_attempted: bool = False
    restore_last_good: bool = False

    def __post_init__(self) -> None:
        if self.turn_sequence is not None and self.turn_sequence < 1:
            raise ValueError("turn_sequence must be >= 1 when present")
        if self.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}:
            if not all((self.answer.strip(), self.context_reference, self.provider, self.model)):
                raise ValueError(
                    "successful agent result requires answer, context, provider, model"
                )
            if self.error_message is not None:
                raise ValueError("successful agent result cannot have an error")
            if self.status is AgentTurnStatus.PARTIAL and not self.tool_results:
                raise ValueError("partial agent result requires tool results")
        elif self.answer or not self.error_message:
            raise ValueError("unavailable/failed agent result requires only an error message")


@dataclass(frozen=True)
class AgentTurnPolicy:
    enabled: bool
    configured_provider: str
    model_unavailable_reason: AgentModelUnavailableReason | None = None
    max_question_chars: int = 2_000
    max_output_tokens: int = 500

    def __post_init__(self) -> None:
        if self.max_question_chars <= 0 or self.max_output_tokens <= 0:
            raise ValueError("agent limits must be positive")


def _json_value(value: Any, *, exclude_context_reference: bool = False) -> Any:
    if is_dataclass(value):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in fields(value)
            if not (exclude_context_reference and item.name == "context_reference")
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value
