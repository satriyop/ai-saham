"""Shared signal scoring configuration dataclasses.

These frozen config types parameterize the pure conviction scorers in
``company_quality_scoring``, consumed by ``CompanyQualityContextEvidenceBuilder``.
They live in a standalone config module (not inside a use case) so scoring
functions and their callers can depend on them without an
application-service → use-case import.

Layer: Application (configuration only). Depends on stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeasonalityScoringConfig:
    tailwind_min_avg_return_pct: float = 0.0
    tailwind_min_win_rate_pct: float = 50.0
    headwind_max_avg_return_pct: float = 0.0
    headwind_max_win_rate_pct: float = 50.0


@dataclass(frozen=True)
class AnalystScoringConfig:
    buy_score_max_points: float = 60.0
    upside_score_max_points: float = 40.0
    upside_cap_pct: float = 30.0


@dataclass(frozen=True)
class ForwardPeScoringConfig:
    very_cheap_pe: float = 10.0
    cheap_pe: float = 15.0
    fair_pe: float = 20.0
    expensive_pe: float = 30.0
    very_cheap_score: float = 95.0
    cheap_score: float = 75.0
    fair_score: float = 50.0
    expensive_score: float = 25.0
    post_expensive_pe_step: float = 10.0
    post_expensive_score_decay: float = 15.0


@dataclass(frozen=True)
class BandarScoringConfig:
    mandatory_signal_count: int = 3
    signal_score_unit: int = 2
    default_max_range: int = 6


@dataclass(frozen=True)
class SignalScoringConfig:
    bandar: BandarScoringConfig = field(default_factory=BandarScoringConfig)
    seasonality: SeasonalityScoringConfig = field(default_factory=SeasonalityScoringConfig)
    analyst: AnalystScoringConfig = field(default_factory=AnalystScoringConfig)
    forward_pe: ForwardPeScoringConfig = field(default_factory=ForwardPeScoringConfig)
