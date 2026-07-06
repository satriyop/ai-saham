"""Signal forward labels for replayable ticker-level outcome attribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


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
class SignalObservationFingerprint:
    """Raw signal-time facts persisted for later attribution."""

    setup_family: str | None = None
    setup_phase: str | None = None
    setup_phase_previous: str | None = None
    phase_sequence_valid: bool | None = None
    phase_age_sessions: int | None = None
    phase_strength: float | None = None
    phase_reasons: tuple[str, ...] = ()
    phase_history: tuple[dict[str, Any], ...] = ()
    phase_coverage_score: float | None = None
    phase_conviction_score: float | None = None
    rsi: float | None = None
    bb_width_pctile: float | None = None
    vwap_position: float | None = None
    rs_vs_ihsg: float | None = None
    volume_ratio: float | None = None
    cnfb: float | None = None
    foreign_participation: float | None = None
    foreign_concentration: float | None = None
    domestic_broker_accumulation: float | None = None
    market_regime: dict[str, Any] = field(default_factory=dict)
    coverage: float | None = None
    conviction: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_family": self.setup_family,
            "setup_phase": self.setup_phase,
            "setup_phase_previous": self.setup_phase_previous,
            "phase_sequence_valid": self.phase_sequence_valid,
            "phase_age_sessions": self.phase_age_sessions,
            "phase_strength": self.phase_strength,
            "phase_reasons": list(self.phase_reasons),
            "phase_history": [dict(entry) for entry in self.phase_history],
            "phase_coverage_score": self.phase_coverage_score,
            "phase_conviction_score": self.phase_conviction_score,
            "rsi": self.rsi,
            "bb_width_pctile": self.bb_width_pctile,
            "vwap_position": self.vwap_position,
            "rs_vs_ihsg": self.rs_vs_ihsg,
            "volume_ratio": self.volume_ratio,
            "cnfb": self.cnfb,
            "foreign_participation": self.foreign_participation,
            "foreign_concentration": self.foreign_concentration,
            "domestic_broker_accumulation": self.domestic_broker_accumulation,
            "market_regime": dict(self.market_regime),
            "coverage": self.coverage,
            "conviction": self.conviction,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalObservationFingerprint":
        regime = data.get("market_regime")
        if regime is None and data.get("market_regime_at_signal") is not None:
            regime = {
                "regime": data.get("market_regime_at_signal"),
                "regime_confidence": data.get("regime_confidence_at_signal"),
                "regime_stability": data.get("regime_stability_at_signal"),
            }
            if data.get("decision_constraints") is not None:
                regime["decision_constraints"] = data.get("decision_constraints")
        return cls(
            setup_family=data.get("setup_family"),
            setup_phase=data.get("setup_phase") or data.get("setup_phase_current"),
            setup_phase_previous=data.get("setup_phase_previous"),
            phase_sequence_valid=_optional_bool(data.get("phase_sequence_valid")),
            phase_age_sessions=_optional_int(data.get("phase_age_sessions")),
            phase_strength=_optional_float(data.get("phase_strength")),
            phase_reasons=tuple(str(v) for v in data.get("phase_reasons") or ()),
            phase_history=tuple(
                dict(v) for v in data.get("phase_history") or () if isinstance(v, dict)
            ),
            phase_coverage_score=_optional_float(data.get("phase_coverage_score")),
            phase_conviction_score=_optional_float(data.get("phase_conviction_score")),
            rsi=_optional_float(data.get("rsi", data.get("rsi_at_signal"))),
            bb_width_pctile=_optional_float(
                data.get("bb_width_pctile", data.get("bb_width_pctile_at_signal"))
            ),
            vwap_position=_optional_float(
                data.get("vwap_position", data.get("vwap_position_at_signal"))
            ),
            rs_vs_ihsg=_optional_float(
                data.get("rs_vs_ihsg", data.get("rs_vs_ihsg_20d_at_signal"))
            ),
            volume_ratio=_optional_float(
                data.get("volume_ratio", data.get("volume_ratio_at_signal"))
            ),
            cnfb=_optional_float(data.get("cnfb", data.get("cnfb_20d_at_signal"))),
            foreign_participation=_optional_float(
                data.get(
                    "foreign_participation",
                    data.get("foreign_participation_at_signal"),
                )
            ),
            foreign_concentration=_optional_float(
                data.get(
                    "foreign_concentration",
                    data.get("foreign_concentration_at_signal"),
                )
            ),
            domestic_broker_accumulation=_optional_float(
                data.get(
                    "domestic_broker_accumulation",
                    data.get("domestic_broker_accumulation_at_signal"),
                )
            ),
            market_regime=dict(regime or {}),
            coverage=_optional_float(data.get("coverage", data.get("coverage_score"))),
            conviction=_optional_float(data.get("conviction", data.get("conviction_score"))),
        )


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
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if self.entry_reference_price is not None and self.entry_reference_price <= Decimal("0"):
            raise ValueError("entry_reference_price must be positive when provided")
        if self.schema_version != 1:
            raise ValueError(
                f"unsupported signal forward label schema_version={self.schema_version}"
            )
        if self.outcome_label == SignalForwardOutcome.UNAVAILABLE and not self.unavailable_reason:
            raise ValueError("UNAVAILABLE labels require unavailable_reason")
        if self.outcome_label != SignalForwardOutcome.UNAVAILABLE and self.unavailable_reason:
            raise ValueError("available labels must not set unavailable_reason")

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
            "fingerprint": self.fingerprint.to_dict(),
            "observation_captured_at": (
                self.observation_captured_at.isoformat() if self.observation_captured_at else None
            ),
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
            schema_version=int(data.get("schema_version", 1)),
        )


def _parse_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _parse_optional_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    return _parse_date(value)


def _parse_optional_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
