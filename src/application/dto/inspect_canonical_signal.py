"""DTOs for read-only canonical SignalEngine inspection (DQ-007).

Layer: Application (DTO)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from src.application.dto.assess_signal import AssessSignalResponse


class InspectCanonicalSignalContract(str, Enum):
    ACCUMULATION_FLOW = "accumulation-flow"


class InspectCanonicalSignalStatus(str, Enum):
    OK = "OK"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class InspectCanonicalSignalRequest:
    ticker: str
    as_of_date: date | None = None
    window_days: int = 7
    contract: InspectCanonicalSignalContract = InspectCanonicalSignalContract.ACCUMULATION_FLOW


@dataclass(frozen=True)
class InspectEffectiveSessionView:
    run_at: datetime
    decision_at: datetime
    latest_completed_session: date
    analysis_as_of: date
    market_session_name: str
    is_eod_pending: bool
    resolution_source: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_at": self.run_at.isoformat(),
            "decision_at": self.decision_at.isoformat(),
            "latest_completed_session": self.latest_completed_session.isoformat(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "market_session_name": self.market_session_name,
            "is_eod_pending": self.is_eod_pending,
            "resolution_source": self.resolution_source,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class InspectCanonicalSignalResponse:
    status: InspectCanonicalSignalStatus
    contract: InspectCanonicalSignalContract
    ticker: str
    as_of_date: date
    effective_session: InspectEffectiveSessionView | None = None
    assessment: AssessSignalResponse | None = None
    screen_result: str | None = None
    reasons: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize with canonical score/coverage terminology (no factors.*)."""
        assessment_payload: dict[str, Any] | None = None
        if self.assessment is not None:
            assessment_payload = {
                "ticker": self.assessment.ticker,
                "score": self.assessment.assessment.score,
                "strength": self.assessment.assessment.strength.value,
                "entry_quality": self.assessment.assessment.entry_quality.value,
                "signal_authority_coverage": self.assessment.signal_authority_coverage,
                "signal_score_raw": self.assessment.signal_score_raw,
                "raw_group_score": self.assessment.raw_group_score,
                "raw_exact_score": self.assessment.raw_exact_score,
                "coverage_warning": self.assessment.coverage_warning,
                "active_flags": list(self.assessment.active_flags),
                "flag_adjustment": self.assessment.flag_adjustment,
                "breakdown": self.assessment.assessment.breakdown_dict,
                "rationale": list(self.assessment.assessment.rationale),
                "legacy_conditioned_score": (self.assessment.assessment.legacy_conditioned_score),
                "legacy_conditioned_score_note": (
                    "regime conditioning diagnostic on the canonical path; "
                    "not the retired six-factor score"
                ),
                "setup_readiness": (
                    self.assessment.setup_readiness.to_dict()
                    if self.assessment.setup_readiness is not None
                    else None
                ),
                "decision_constraints": (
                    self.assessment.assessment.decision_constraints.to_dict()
                    if self.assessment.assessment.decision_constraints is not None
                    else None
                ),
                "setup_source_availability": (
                    self.assessment.setup_source_availability.to_dict()
                    if self.assessment.setup_source_availability is not None
                    else None
                ),
                "flow_source_availability": (
                    self.assessment.flow_source_availability.to_dict()
                    if self.assessment.flow_source_availability is not None
                    else None
                ),
                "availability_enforcement": (
                    self.assessment.availability_enforcement.value
                    if self.assessment.availability_enforcement is not None
                    else None
                ),
                "alpha_trigger_score": (
                    self.assessment.alpha_trigger_score.to_dict()
                    if self.assessment.alpha_trigger_score is not None
                    else None
                ),
            }
        payload = {
            "status": self.status.value,
            "contract": self.contract.value,
            "ticker": self.ticker,
            "as_of_date": self.as_of_date.isoformat(),
            "effective_session": (
                self.effective_session.to_dict() if self.effective_session is not None else None
            ),
            "screen_result": self.screen_result,
            "assessment": assessment_payload,
            "reasons": list(self.reasons),
            "notes": list(self.notes),
        }
        # Hard guard: never expose retired six-factor surfaces.
        assert "factors" not in payload
        if assessment_payload is not None:
            assert "factors" not in assessment_payload
        return payload
