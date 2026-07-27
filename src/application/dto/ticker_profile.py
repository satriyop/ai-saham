"""TickerProfile DTOs — application data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus


@dataclass(frozen=True)
class TickerProfileRequest:
    ticker: str
    snapshot_date: date
    candles: tuple[Candle, ...]
    broker_daily_flows: tuple[BrokerDailyFlow, ...]
    broker_summaries: tuple[BrokerSummary, ...]
    market_cap_idr: Decimal | None
    sector: str | None
    sub_sector: str | None


@dataclass(frozen=True)
class TickerProfileConfig:
    evidence_status: EvidenceStatus
    profile_window_days: int
    market_cap_large: int
    market_cap_mid: int
    market_cap_small: int
    index_membership_scores: dict[str, float]
    liquidity_high: float
    liquidity_low: float
    volatility_high: float
    volatility_low: float
    sparse_history_threshold: int
    conservative_fallback_confidence: float
    exposure_weights: dict[str, dict[str, float]] = field(default_factory=dict)

    def validate(self) -> None:
        for name, score in self.index_membership_scores.items():
            if not 0.0 <= float(score) <= 1.0:
                raise ValueError(f"index_membership_score for {name} must be in [0,1]")
        for profile, weights in self.exposure_weights.items():
            if not weights:
                continue
            total = 0.0
            for dim, weight in weights.items():
                weight_float = float(weight)
                if weight_float < 0.0:
                    raise ValueError(f"exposure weight {profile}.{dim} must be non-negative")
                total += weight_float
            if abs(total - 1.0) > 0.0001:
                raise ValueError(f"exposure weights for {profile} must sum to 1.0, got {total:.4f}")

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "TickerProfileConfig":
        block = raw.get("ticker_profile", raw)
        caps = block.get("market_cap_thresholds_idr", {}) or {}
        liq = block.get("liquidity_thresholds", {}) or {}
        vol = block.get("volatility_thresholds", {}) or {}
        status = EvidenceStatus(block.get("evidence_status", "DIAGNOSTIC"))
        return cls(
            evidence_status=status,
            profile_window_days=int(block.get("profile_window_days", 30)),
            market_cap_large=int(caps.get("large", 10_000_000_000_000)),
            market_cap_mid=int(caps.get("mid", 1_000_000_000_000)),
            market_cap_small=int(caps.get("small", 200_000_000_000)),
            index_membership_scores={
                str(k): float(v) for k, v in (block.get("index_membership_scores") or {}).items()
            },
            liquidity_high=float(liq.get("high_daily_value_idr", 50_000_000_000)),
            liquidity_low=float(liq.get("low_daily_value_idr", 500_000_000)),
            volatility_high=float(vol.get("high_atr_pct", 0.050)),
            volatility_low=float(vol.get("low_atr_pct", 0.005)),
            sparse_history_threshold=int(block.get("sparse_history_threshold", 10)),
            conservative_fallback_confidence=float(
                block.get("conservative_fallback_confidence", 0.30)
            ),
            exposure_weights={
                str(profile): {str(dim): float(weight) for dim, weight in (dims or {}).items()}
                for profile, dims in (block.get("exposure_weights") or {}).items()
            },
        )
