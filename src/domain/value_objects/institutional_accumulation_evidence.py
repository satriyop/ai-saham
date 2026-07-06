"""Diagnostic institutional accumulation evidence (two-track foreign + domestic flow)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class EvidenceStatus(Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    LOW_WEIGHT = "LOW_WEIGHT"
    PRODUCTION = "PRODUCTION"


@dataclass(frozen=True)
class ForeignInstitutionalTrack:
    foreign_participation_score: float | None
    foreign_cr4_score: float | None
    foreign_cr8_score: float | None
    cnfb_divergence_score: float | None
    foreign_vwap_distance_score: float | None
    coverage_score: float
    conviction_score: float
    evidence_status: EvidenceStatus
    reasons: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "foreign_participation_score",
            "foreign_cr4_score",
            "foreign_cr8_score",
            "cnfb_divergence_score",
            "foreign_vwap_distance_score",
            "coverage_score",
            "conviction_score",
        ):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "foreign_participation_score": self.foreign_participation_score,
            "foreign_cr4_score": self.foreign_cr4_score,
            "foreign_cr8_score": self.foreign_cr8_score,
            "cnfb_divergence_score": self.cnfb_divergence_score,
            "foreign_vwap_distance_score": self.foreign_vwap_distance_score,
            "coverage_score": self.coverage_score,
            "conviction_score": self.conviction_score,
            "evidence_status": self.evidence_status.value,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ForeignInstitutionalTrack":
        return cls(
            foreign_participation_score=_optional_float(
                data.get("foreign_participation_score")
            ),
            foreign_cr4_score=_optional_float(data.get("foreign_cr4_score")),
            foreign_cr8_score=_optional_float(data.get("foreign_cr8_score")),
            cnfb_divergence_score=_optional_float(data.get("cnfb_divergence_score")),
            foreign_vwap_distance_score=_optional_float(
                data.get("foreign_vwap_distance_score")
            ),
            coverage_score=float(data.get("coverage_score") or 0.0),
            conviction_score=float(data.get("conviction_score") or 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status") or EvidenceStatus.DIAGNOSTIC.value
            ),
            reasons=tuple(str(v) for v in data.get("reasons") or ()),
            unavailable_reasons=tuple(
                str(v) for v in data.get("unavailable_reasons") or ()
            ),
        )


@dataclass(frozen=True)
class DomesticBandarTrack:
    broker_consistency_score: float | None
    broker_reversal_score: float | None
    accumulation_session_ratio: float | None
    domestic_buy_vwap_distance_score: float | None
    broker_hhi_divergence_score: float | None
    bandar_broad_score_normalized: float | None
    bandar_accumulation_score_normalized: float | None
    coverage_score: float
    conviction_score: float
    evidence_status: EvidenceStatus
    reasons: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "broker_consistency_score",
            "broker_reversal_score",
            "accumulation_session_ratio",
            "domestic_buy_vwap_distance_score",
            "broker_hhi_divergence_score",
            "bandar_broad_score_normalized",
            "bandar_accumulation_score_normalized",
            "coverage_score",
            "conviction_score",
        ):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_consistency_score": self.broker_consistency_score,
            "broker_reversal_score": self.broker_reversal_score,
            "accumulation_session_ratio": self.accumulation_session_ratio,
            "domestic_buy_vwap_distance_score": self.domestic_buy_vwap_distance_score,
            "broker_hhi_divergence_score": self.broker_hhi_divergence_score,
            "bandar_broad_score_normalized": self.bandar_broad_score_normalized,
            "bandar_accumulation_score_normalized": (
                self.bandar_accumulation_score_normalized
            ),
            "coverage_score": self.coverage_score,
            "conviction_score": self.conviction_score,
            "evidence_status": self.evidence_status.value,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomesticBandarTrack":
        return cls(
            broker_consistency_score=_optional_float(
                data.get("broker_consistency_score")
            ),
            broker_reversal_score=_optional_float(data.get("broker_reversal_score")),
            accumulation_session_ratio=_optional_float(
                data.get("accumulation_session_ratio")
            ),
            domestic_buy_vwap_distance_score=_optional_float(
                data.get("domestic_buy_vwap_distance_score")
            ),
            broker_hhi_divergence_score=_optional_float(
                data.get("broker_hhi_divergence_score")
            ),
            bandar_broad_score_normalized=_optional_float(
                data.get("bandar_broad_score_normalized")
            ),
            bandar_accumulation_score_normalized=_optional_float(
                data.get("bandar_accumulation_score_normalized")
            ),
            coverage_score=float(data.get("coverage_score") or 0.0),
            conviction_score=float(data.get("conviction_score") or 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status") or EvidenceStatus.DIAGNOSTIC.value
            ),
            reasons=tuple(str(v) for v in data.get("reasons") or ()),
            unavailable_reasons=tuple(
                str(v) for v in data.get("unavailable_reasons") or ()
            ),
        )


@dataclass(frozen=True)
class CounterpartyTransferEvidence:
    transfer_asymmetry_score: float | None
    buy_side_hhi: float | None
    sell_side_hhi: float | None
    coverage_score: float
    conviction_score: float
    evidence_status: EvidenceStatus
    unavailable_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        # buy_side_hhi/sell_side_hhi are raw HHI values, not bounded to [0,1].
        for name in ("transfer_asymmetry_score", "coverage_score", "conviction_score"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_asymmetry_score": self.transfer_asymmetry_score,
            "buy_side_hhi": self.buy_side_hhi,
            "sell_side_hhi": self.sell_side_hhi,
            "coverage_score": self.coverage_score,
            "conviction_score": self.conviction_score,
            "evidence_status": self.evidence_status.value,
            "unavailable_reasons": list(self.unavailable_reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CounterpartyTransferEvidence":
        return cls(
            transfer_asymmetry_score=_optional_float(
                data.get("transfer_asymmetry_score")
            ),
            buy_side_hhi=_optional_float(data.get("buy_side_hhi")),
            sell_side_hhi=_optional_float(data.get("sell_side_hhi")),
            coverage_score=float(data.get("coverage_score") or 0.0),
            conviction_score=float(data.get("conviction_score") or 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status") or EvidenceStatus.DIAGNOSTIC.value
            ),
            unavailable_reasons=tuple(
                str(v) for v in data.get("unavailable_reasons") or ()
            ),
        )


@dataclass(frozen=True)
class InstitutionalAccumulationEvidence:
    ticker: str
    snapshot_date: date
    foreign_institutional_track: ForeignInstitutionalTrack
    domestic_bandar_track: DomesticBandarTrack
    counterparty_transfer: CounterpartyTransferEvidence | None
    coverage_score: float
    conviction_score: float
    evidence_status: EvidenceStatus
    reasons: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        for name in ("coverage_score", "conviction_score"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "foreign_institutional_track": self.foreign_institutional_track.to_dict(),
            "domestic_bandar_track": self.domestic_bandar_track.to_dict(),
            "counterparty_transfer": (
                self.counterparty_transfer.to_dict()
                if self.counterparty_transfer is not None
                else None
            ),
            "coverage_score": self.coverage_score,
            "conviction_score": self.conviction_score,
            "evidence_status": self.evidence_status.value,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstitutionalAccumulationEvidence":
        counterparty = data.get("counterparty_transfer")
        return cls(
            ticker=str(data["ticker"]).upper(),
            snapshot_date=(
                data["snapshot_date"]
                if isinstance(data["snapshot_date"], date)
                else date.fromisoformat(str(data["snapshot_date"]))
            ),
            foreign_institutional_track=ForeignInstitutionalTrack.from_dict(
                data.get("foreign_institutional_track") or {}
            ),
            domestic_bandar_track=DomesticBandarTrack.from_dict(
                data.get("domestic_bandar_track") or {}
            ),
            counterparty_transfer=(
                CounterpartyTransferEvidence.from_dict(counterparty)
                if isinstance(counterparty, dict)
                else None
            ),
            coverage_score=float(data.get("coverage_score") or 0.0),
            conviction_score=float(data.get("conviction_score") or 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status") or EvidenceStatus.DIAGNOSTIC.value
            ),
            reasons=tuple(str(v) for v in data.get("reasons") or ()),
            unavailable_reasons=tuple(
                str(v) for v in data.get("unavailable_reasons") or ()
            ),
            metadata=dict(data.get("metadata") or {}),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
