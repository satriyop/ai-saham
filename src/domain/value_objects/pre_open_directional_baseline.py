"""Typed output contract for the deterministic pre-open directional baseline.

Layer: Domain (pure value objects, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

PRE_OPEN_DIRECTIONAL_BASELINE_CONTRACT = "pre_open_directional_baseline.v1"


class PreOpenDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    CONFLICTED = "CONFLICTED"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class PreOpenDirectionConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PreOpenAuctionQuality(str, Enum):
    RELIABLE = "RELIABLE"
    CAUTION = "CAUTION"
    UNRELIABLE = "UNRELIABLE"


@dataclass(frozen=True)
class PreOpenBaselineFactors:
    iep_direction: str
    book_pressure_state: str
    participation_state: str
    iep_gap_pct: float | None
    book_pressure: float | None
    delta_iev: int | None
    delta_iev_ratio: float | None
    iev_intensity: float | None
    spread_pct: float | None
    rsi_extension: bool
    unusual_volume: bool

    def to_dict(self) -> dict:
        return {
            "iep_direction": self.iep_direction,
            "book_pressure_state": self.book_pressure_state,
            "participation_state": self.participation_state,
            "iep_gap_pct": self.iep_gap_pct,
            "book_pressure": self.book_pressure,
            "delta_iev": self.delta_iev,
            "delta_iev_ratio": self.delta_iev_ratio,
            "iev_intensity": self.iev_intensity,
            "spread_pct": self.spread_pct,
            "rsi_extension": self.rsi_extension,
            "unusual_volume": self.unusual_volume,
        }


@dataclass(frozen=True)
class PreOpenBaselineAssessment:
    contract: str
    direction: PreOpenDirection
    confidence: PreOpenDirectionConfidence
    auction_quality: PreOpenAuctionQuality
    raw_score: int
    factors: PreOpenBaselineFactors
    rationale: tuple[str, ...]
    quality_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.contract != PRE_OPEN_DIRECTIONAL_BASELINE_CONTRACT:
            raise ValueError(
                f"pre-open baseline contract must be {PRE_OPEN_DIRECTIONAL_BASELINE_CONTRACT!r}"
            )
        if not 0 <= self.raw_score <= 100:
            raise ValueError("pre-open baseline raw_score must be 0-100")

    def to_dict(self) -> dict:
        return {
            "contract": self.contract,
            "direction": self.direction.value,
            "confidence": self.confidence.value,
            "auction_quality": self.auction_quality.value,
            "raw_score": self.raw_score,
            "factors": self.factors.to_dict(),
            "rationale": list(self.rationale),
            "quality_reasons": list(self.quality_reasons),
        }
