"""Ticker profile snapshot — deterministic per-ticker behavior classification (Phase F).

DIAGNOSTIC-ONLY: persisted at observation time for replay and attribution.
Never fed into SignalEngine scoring or DecisionPolicy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus


@dataclass(frozen=True)
class TickerProfileSnapshot:
    ticker: str
    snapshot_date: date
    epoch: str                               # "YYYY-MM" — monthly cadence
    primary_profile: str                     # "foreign_institutional"|"domestic_bandar"|"retail_speculative"|"unclassified"|"unknown"
    profile_confidence: float                # [0,1]; exposure margin (primary − second)
    liquidity_score: float | None            # [0,1]; avg daily turnover normalized
    broker_concentration_score: float | None # [0,1]; domestic buy-side HHI
    foreign_flow_score: float | None         # [0,1]; avg foreign participation ratio
    volatility_score: float | None           # [0,1]; ATR/price normalized (higher = more volatile)
    index_membership_score: float | None     # [0,1]; best index score; 0.0 when in no index
    market_cap_bucket: str | None            # "large"|"mid"|"small"|"micro"|"UNKNOWN"
    sector: str | None
    sub_sector: str | None
    index_memberships: tuple[str, ...]       # e.g. ("lq45", "idx80")
    coverage_score: float                    # available dimensions / 5
    evidence_status: EvidenceStatus          # always DIAGNOSTIC in Phase F
    reasons: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]
    # Market-cap / liquidity tier (behaviorally orthogonal to primary_profile).
    market_tier: str | None = None           # "blue_chip"|"second_liner"|"third_liner"|"speculative"|"unknown"
    # Soft behavioral exposures — a simplex over the three canonical profiles.
    foreign_institutional_exposure: float | None = None   # [0,1]
    domestic_bandar_exposure: float | None = None         # [0,1]
    retail_speculative_exposure: float | None = None      # [0,1]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        for name in (
            "liquidity_score",
            "broker_concentration_score",
            "foreign_flow_score",
            "volatility_score",
            "index_membership_score",
            "profile_confidence",
            "coverage_score",
            "foreign_institutional_exposure",
            "domestic_bandar_exposure",
            "retail_speculative_exposure",
        ):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {value}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "epoch": self.epoch,
            "primary_profile": self.primary_profile,
            "profile_confidence": self.profile_confidence,
            "liquidity_score": self.liquidity_score,
            "broker_concentration_score": self.broker_concentration_score,
            "foreign_flow_score": self.foreign_flow_score,
            "volatility_score": self.volatility_score,
            "index_membership_score": self.index_membership_score,
            "market_cap_bucket": self.market_cap_bucket,
            "sector": self.sector,
            "sub_sector": self.sub_sector,
            "index_memberships": list(self.index_memberships),
            "coverage_score": self.coverage_score,
            "evidence_status": self.evidence_status.value,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
            "market_tier": self.market_tier,
            "foreign_institutional_exposure": self.foreign_institutional_exposure,
            "domestic_bandar_exposure": self.domestic_bandar_exposure,
            "retail_speculative_exposure": self.retail_speculative_exposure,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TickerProfileSnapshot":
        raw_date = data.get("snapshot_date") or data.get("date")
        snap_date = (
            raw_date
            if isinstance(raw_date, date)
            else date.fromisoformat(str(raw_date))
            if raw_date
            else date.today()
        )
        return cls(
            ticker=str(data.get("ticker") or "").upper(),
            snapshot_date=snap_date,
            epoch=str(data.get("epoch") or ""),
            primary_profile=str(
                data.get("primary_profile") or data.get("profile_label") or "unknown"
            ),
            profile_confidence=float(data.get("profile_confidence") or 0.0),
            liquidity_score=_optional_float(data.get("liquidity_score")),
            broker_concentration_score=_optional_float(
                data.get("broker_concentration_score")
            ),
            foreign_flow_score=_optional_float(data.get("foreign_flow_score")),
            volatility_score=_optional_float(data.get("volatility_score")),
            index_membership_score=_optional_float(data.get("index_membership_score")),
            market_cap_bucket=data.get("market_cap_bucket"),
            sector=data.get("sector"),
            sub_sector=data.get("sub_sector"),
            index_memberships=tuple(
                str(v) for v in data.get("index_memberships") or ()
            ),
            coverage_score=float(data.get("coverage_score") or 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status") or EvidenceStatus.DIAGNOSTIC.value
            ),
            reasons=tuple(str(v) for v in data.get("reasons") or ()),
            unavailable_reasons=tuple(
                str(v) for v in data.get("unavailable_reasons") or ()
            ),
            market_tier=data.get("market_tier"),
            foreign_institutional_exposure=_optional_float(
                data.get("foreign_institutional_exposure")
            ),
            domestic_bandar_exposure=_optional_float(
                data.get("domestic_bandar_exposure")
            ),
            retail_speculative_exposure=_optional_float(
                data.get("retail_speculative_exposure")
            ),
            metadata=dict(data.get("metadata") or {}),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
