"""Signal forward labels for replayable ticker-level outcome attribution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from src.domain.value_objects.signal_label_parsing import (
    _optional_bool,
    _optional_float,
    _optional_int,
    _parse_date,
    _parse_optional_date,
    _parse_optional_datetime,
)
from src.domain.value_objects.signal_artifact_identity import (
    SignalArtifactIdentity,
)
from src.domain.value_objects.signal_artifact_schema import (
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_observation_fingerprint import (
    SignalObservationFingerprint,
)


class SignalLabelHorizon(Enum):
    """Supported Phase B label horizons."""

    TACTICAL_3D = "TACTICAL_3D"
    SWING_10D = "SWING_10D"
    ACCUM_20D = "ACCUM_20D"

    @property
    def trading_days(self) -> int:
        return {
            SignalLabelHorizon.TACTICAL_3D: 3,
            SignalLabelHorizon.SWING_10D: 10,
            SignalLabelHorizon.ACCUM_20D: 20,
        }[self]


class SignalForwardOutcome(Enum):
    """Discrete deterministic outcome label."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    NEUTRAL = "NEUTRAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class SignalForwardLabel:
    """Deterministic forward outcome label for one saved signal observation."""

    ticker: str
    signal_date: date
    horizon: SignalLabelHorizon
    entry_reference_price: Decimal | None
    label_window_start: date | None
    label_window_end: date | None
    close_return: float | None
    max_forward_return: float | None
    max_adverse_excursion: float | None
    days_to_peak: int | None
    days_to_trough: int | None
    stop_would_trigger: bool | None
    target_would_trigger: bool | None
    outcome_label: SignalForwardOutcome
    unavailable_reason: str | None
    fingerprint: SignalObservationFingerprint
    observation_captured_at: datetime | None = None
    # Effective-session provenance (DQ-002E). Copied verbatim from the source
    # CandidateObservation at label-generation time — never derived from
    # signal_date and never resolved fresh here.
    decision_at: datetime | None = None
    latest_completed_session: date | None = None
    analysis_as_of: date | None = None
    market_session_name: str | None = None
    is_eod_pending: bool | None = None
    resolution_source: str | None = None
    resolution_notes: tuple[str, ...] = ()
    # HIGH-2: new labels are schema 2 (canonical). Schema 1 remains
    # diagnostic-readable but is excluded from canonical readiness/tuning/
    # promotion — see report_signal_readiness_use_case.py.
    schema_version: int = SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
    # Repository metadata: pre-resolved artifact identity. Never serialized
    # in to_dict()/from_dict(). See ARTIFACT-IDENTITY Slice 4.
    artifact_identity: SignalArtifactIdentity | None = None

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if self.entry_reference_price is not None and self.entry_reference_price <= Decimal("0"):
            raise ValueError("entry_reference_price must be positive when provided")
        if self.schema_version < 1 or self.schema_version > SIGNAL_FORWARD_LABEL_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported signal forward label schema_version={self.schema_version}"
            )
        if self.outcome_label == SignalForwardOutcome.UNAVAILABLE and not self.unavailable_reason:
            raise ValueError("UNAVAILABLE labels require unavailable_reason")
        if self.outcome_label != SignalForwardOutcome.UNAVAILABLE and self.unavailable_reason:
            raise ValueError("available labels must not set unavailable_reason")

    def fingerprint_payload(self) -> dict[str, Any]:
        if self.schema_version == 1:
            return self.fingerprint.to_dict()
        if self.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION:
            return self.fingerprint.to_canonical_dict()
        raise ValueError(
            f"unsupported signal forward label schema_version={self.schema_version}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticker": self.ticker,
            "signal_date": self.signal_date.isoformat(),
            "horizon": self.horizon.value,
            "entry_reference_price": (
                str(self.entry_reference_price) if self.entry_reference_price is not None else None
            ),
            "label_window_start": (
                self.label_window_start.isoformat() if self.label_window_start else None
            ),
            "label_window_end": (
                self.label_window_end.isoformat() if self.label_window_end else None
            ),
            "close_return": self.close_return,
            "max_forward_return": self.max_forward_return,
            "max_adverse_excursion": self.max_adverse_excursion,
            "days_to_peak": self.days_to_peak,
            "days_to_trough": self.days_to_trough,
            "stop_would_trigger": self.stop_would_trigger,
            "target_would_trigger": self.target_would_trigger,
            "outcome_label": self.outcome_label.value,
            "unavailable_reason": self.unavailable_reason,
            "fingerprint": self.fingerprint_payload(),
            "observation_captured_at": (
                self.observation_captured_at.isoformat() if self.observation_captured_at else None
            ),
            "decision_at": self.decision_at.isoformat() if self.decision_at else None,
            "latest_completed_session": (
                self.latest_completed_session.isoformat()
                if self.latest_completed_session
                else None
            ),
            "analysis_as_of": self.analysis_as_of.isoformat() if self.analysis_as_of else None,
            "market_session_name": self.market_session_name,
            "is_eod_pending": self.is_eod_pending,
            "resolution_source": self.resolution_source,
            "resolution_notes": list(self.resolution_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalForwardLabel":
        return cls(
            ticker=str(data["ticker"]).upper(),
            signal_date=_parse_date(data["signal_date"]),
            horizon=SignalLabelHorizon(data["horizon"]),
            entry_reference_price=(
                Decimal(str(data["entry_reference_price"]))
                if data.get("entry_reference_price") is not None
                else None
            ),
            label_window_start=_parse_optional_date(data.get("label_window_start")),
            label_window_end=_parse_optional_date(data.get("label_window_end")),
            close_return=_optional_float(data.get("close_return")),
            max_forward_return=_optional_float(data.get("max_forward_return")),
            max_adverse_excursion=_optional_float(data.get("max_adverse_excursion")),
            days_to_peak=_optional_int(data.get("days_to_peak")),
            days_to_trough=_optional_int(data.get("days_to_trough")),
            stop_would_trigger=_optional_bool(data.get("stop_would_trigger")),
            target_would_trigger=_optional_bool(data.get("target_would_trigger")),
            outcome_label=SignalForwardOutcome(data["outcome_label"]),
            unavailable_reason=data.get("unavailable_reason"),
            fingerprint=SignalObservationFingerprint.from_dict(data.get("fingerprint") or {}),
            observation_captured_at=_parse_optional_datetime(data.get("observation_captured_at")),
            decision_at=_parse_optional_datetime(data.get("decision_at")),
            latest_completed_session=_parse_optional_date(data.get("latest_completed_session")),
            analysis_as_of=_parse_optional_date(data.get("analysis_as_of")),
            market_session_name=data.get("market_session_name"),
            is_eod_pending=_optional_bool(data.get("is_eod_pending")),
            resolution_source=data.get("resolution_source"),
            resolution_notes=tuple(data.get("resolution_notes") or ()),
            schema_version=int(data.get("schema_version", 1)),
        )
