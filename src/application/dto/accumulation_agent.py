"""Channel-neutral DTOs for one read-only accumulation commentary turn."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from src.application.dto.accumulation_screen import AccumulationCandidate
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


@dataclass(frozen=True)
class AgentTurnRequest:
    user_text: str
    candidate: AccumulationCandidate


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
class AgentAccumulationContext:
    schema_id: str
    context_reference: str
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

    def canonical_payload(self) -> dict[str, Any]:
        return _json_value(self, exclude_context_reference=True)


@dataclass(frozen=True)
class AgentModelRequest:
    system_policy: str
    user_text: str
    context: AgentAccumulationContext
    max_output_tokens: int
    tool_definitions: tuple[AgentToolDefinition, ...] = ()
    tool_choice: AgentModelToolChoice = AgentModelToolChoice.NONE
    prior_tool_calls: tuple[AgentModelToolCall, ...] = ()
    tool_results: tuple[AgentToolExecutionResult, ...] = ()
    session_pack: AgentSessionPack | None = None

    def __post_init__(self) -> None:
        if self.max_output_tokens <= 0:
            raise ValueError("agent model output limit must be positive")
        if self.tool_choice is AgentModelToolChoice.AUTO:
            if not self.tool_definitions or self.prior_tool_calls or self.tool_results:
                raise ValueError("initial tool request requires definitions and no prior results")
        elif self.prior_tool_calls or self.tool_results:
            if not self.tool_definitions or len(self.prior_tool_calls) != len(self.tool_results):
                raise ValueError("final tool request requires matched calls, results, definitions")
            if tuple(call.call_id for call in self.prior_tool_calls) != tuple(
                result.call_id for result in self.tool_results
            ):
                raise ValueError("final tool request call/result identities must match")
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
