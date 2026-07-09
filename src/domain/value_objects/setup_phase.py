"""Setup phase state value objects.

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class SetupPhaseState(str, Enum):
    NONE = "NONE"
    ACCUMULATION = "ACCUMULATION"
    COMPRESSION = "COMPRESSION"
    BREAKOUT_CONFIRMATION = "BREAKOUT_CONFIRMATION"
    EXHAUSTION = "EXHAUSTION"
    DISTRIBUTION = "DISTRIBUTION"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SetupPhaseHistoryEntry:
    phase: SetupPhaseState
    started_at: date | None
    ended_at: date | None
    age_sessions: int
    strength: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    sequence_valid_after_transition: bool | None = None

    def __post_init__(self) -> None:
        _validate_score("strength", self.strength)
        if self.age_sessions < 0:
            raise ValueError("age_sessions must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "age_sessions": self.age_sessions,
            "strength": self.strength,
            "reasons": list(self.reasons),
            "sequence_valid_after_transition": self.sequence_valid_after_transition,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetupPhaseHistoryEntry":
        return cls(
            phase=SetupPhaseState(data["phase"]),
            started_at=_optional_date(data.get("started_at")),
            ended_at=_optional_date(data.get("ended_at")),
            age_sessions=int(data.get("age_sessions", 0)),
            strength=float(data.get("strength", 0.0)),
            reasons=tuple(str(v) for v in data.get("reasons") or ()),
            sequence_valid_after_transition=data.get(
                "sequence_valid_after_transition"
            ),
        )


@dataclass(frozen=True)
class SetupPhaseSnapshot:
    current_phase: SetupPhaseState
    previous_phase: SetupPhaseState | None
    phase_age_sessions: int
    phase_strength: float
    coverage_score: float
    conviction_score: float
    sequence_valid: bool | None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    unavailable_evidence_reasons: tuple[str, ...] = field(default_factory=tuple)
    history: tuple[SetupPhaseHistoryEntry, ...] = field(default_factory=tuple)
    # Explicit dry-up/expansion evidence (Point 3) — None when volume trigger
    # evidence was not computed (e.g. no config/candles supplied to detect()).
    volume_dry_up_ratio: float | None = None
    volume_expansion_ratio: float | None = None
    volume_dry_up_confirmed: bool | None = None
    volume_expansion_confirmed: bool | None = None
    volume_trigger_confirmed: bool | None = None

    def __post_init__(self) -> None:
        if self.phase_age_sessions < 0:
            raise ValueError("phase_age_sessions must be >= 0")
        _validate_score("phase_strength", self.phase_strength)
        _validate_score("coverage_score", self.coverage_score)
        _validate_score("conviction_score", self.conviction_score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_phase": self.current_phase.value,
            "previous_phase": self.previous_phase.value if self.previous_phase else None,
            "phase_age_sessions": self.phase_age_sessions,
            "phase_strength": self.phase_strength,
            "coverage_score": self.coverage_score,
            "conviction_score": self.conviction_score,
            "sequence_valid": self.sequence_valid,
            "reasons": list(self.reasons),
            "unavailable_evidence_reasons": list(self.unavailable_evidence_reasons),
            "history": [entry.to_dict() for entry in self.history],
            "volume_dry_up_ratio": self.volume_dry_up_ratio,
            "volume_expansion_ratio": self.volume_expansion_ratio,
            "volume_dry_up_confirmed": self.volume_dry_up_confirmed,
            "volume_expansion_confirmed": self.volume_expansion_confirmed,
            "volume_trigger_confirmed": self.volume_trigger_confirmed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetupPhaseSnapshot":
        return cls(
            current_phase=SetupPhaseState(data["current_phase"]),
            previous_phase=(
                SetupPhaseState(data["previous_phase"])
                if data.get("previous_phase") else None
            ),
            phase_age_sessions=int(data.get("phase_age_sessions", 0)),
            phase_strength=float(data.get("phase_strength", 0.0)),
            coverage_score=float(data.get("coverage_score", 0.0)),
            conviction_score=float(data.get("conviction_score", 0.0)),
            sequence_valid=data.get("sequence_valid"),
            reasons=tuple(str(v) for v in data.get("reasons") or ()),
            unavailable_evidence_reasons=tuple(
                str(v) for v in data.get("unavailable_evidence_reasons") or ()
            ),
            history=tuple(
                SetupPhaseHistoryEntry.from_dict(v)
                for v in data.get("history") or ()
            ),
            volume_dry_up_ratio=_optional_float(data.get("volume_dry_up_ratio")),
            volume_expansion_ratio=_optional_float(data.get("volume_expansion_ratio")),
            volume_dry_up_confirmed=data.get("volume_dry_up_confirmed"),
            volume_expansion_confirmed=data.get("volume_expansion_confirmed"),
            volume_trigger_confirmed=data.get("volume_trigger_confirmed"),
        )


def _validate_score(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be 0.0-1.0, got {value}")


def _optional_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
