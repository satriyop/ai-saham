"""CompanyQualityContextEvidenceBuilder — application service (Phase I prep).

Computes ticker-alpha / contextual-conviction diagnostics from enrichment already
present on SignalContext: valuation (forward P/E), analyst consensus, insider
net-buy direction, and CAPPED generic seasonality. Calls the SHARED conviction
scorers (company_quality_scoring) — a single source of truth for these
formulas, with no other producer duplicating them.

Design invariants:
- The builder NEVER fetches data. All inputs arrive on the request (SignalContext).
- The builder NEVER raises. On any error the whole snapshot degrades to
  unavailable() with metadata["error"].
- evidence_status is always DIAGNOSTIC in this phase.
- aggregate_score is a COVERAGE-WEIGHTED mean of PRESENT axes only. Missing axes
  lower coverage_score; they do not fabricate a neutral-50. Seasonality carries a
  strictly lower cap weight than the other axes.
- Deferred axes (earnings_trend, event alpha) have no producer and are excluded
  from coverage — recorded as unavailable reasons so Phase I knows they exist.

It MUST NOT compute liquidity, free-float, Piotroski, bandar-distribution, or
technical-gate logic — those remain RiskEngine responsibilities.

Layer: Application. Depends only on domain VOs + application scorers.
No provider/repository/CLI imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from src.application.services.company_quality_scoring import (
    score_analyst,
    score_forward_pe,
    score_insider_activity,
    score_seasonality,
)
from src.application.services.signal_scoring_config import SignalScoringConfig
from src.domain.value_objects.company_quality_context_evidence import (
    CompanyQualityContextEvidence,
)
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.signal_assessment import SignalContext

_DEFAULT_NEUTRAL_SCORE = 50.0


# --------------------------------------------------------------------------- #
# Config dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CompanyQualityContextConfig:
    evidence_status: EvidenceStatus
    valuation_weight: float
    analyst_weight: float
    insider_weight: float
    seasonality_weight: float  # CAP: strictly lower than the others
    scored_axis_count: int

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "CompanyQualityContextConfig":
        weights = raw.get("axis_weights", {}) or {}
        return cls(
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            valuation_weight=float(weights.get("valuation", 1.0)),
            analyst_weight=float(weights.get("analyst", 1.0)),
            insider_weight=float(weights.get("insider", 1.0)),
            seasonality_weight=float(raw.get("seasonality_weight", 0.5)),
            scored_axis_count=int(raw.get("scored_axis_count", 4)),
        )


# --------------------------------------------------------------------------- #
# Request dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CompanyQualityContextRequest:
    ticker: str
    snapshot_date: date
    signal_context: SignalContext


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #


class CompanyQualityContextEvidenceBuilder:
    """Build CompanyQualityContextEvidence from a pre-loaded SignalContext."""

    def __init__(
        self,
        config: CompanyQualityContextConfig,
        scoring: SignalScoringConfig | None = None,
        neutral_score: float = _DEFAULT_NEUTRAL_SCORE,
    ) -> None:
        self._config = config
        # Axis-scorer thresholds live in signal_engine.yaml (factory-owned). For
        # the DIAGNOSTIC producer we default to SignalScoringConfig()'s bare
        # defaults; callers holding the full engine config may override.
        self._scoring = scoring or SignalScoringConfig()
        self._neutral_score = neutral_score

    # --------------------------------------------------------- main build

    def build(self, request: CompanyQualityContextRequest) -> CompanyQualityContextEvidence:
        try:
            return self._build(request)
        except Exception as exc:  # never raise — degrade the whole snapshot
            return CompanyQualityContextEvidence(
                valuation_score=None,
                earnings_trend_score=None,
                analyst_score=None,
                insider_score=None,
                seasonality_score=None,
                present_axes=(),
                aggregate_score=None,
                coverage_score=0.0,
                evidence_status=EvidenceStatus.DIAGNOSTIC,
                reasons=(),
                unavailable_reasons=(f"builder_error:{exc}",),
                metadata={"error": str(exc)},
            )

    def _build(self, request: CompanyQualityContextRequest) -> CompanyQualityContextEvidence:
        ctx = request.signal_context
        cfg = self._config
        scoring = self._scoring
        neutral = self._neutral_score

        reasons: list[str] = []
        unavailable: list[str] = []

        # ── Axis 1: valuation (forward P/E) ──────────────────────────────────
        valuation_score, valuation_present = score_forward_pe(
            ctx,
            very_cheap_pe=scoring.forward_pe.very_cheap_pe,
            cheap_pe=scoring.forward_pe.cheap_pe,
            fair_pe=scoring.forward_pe.fair_pe,
            expensive_pe=scoring.forward_pe.expensive_pe,
            very_cheap_score=scoring.forward_pe.very_cheap_score,
            cheap_score=scoring.forward_pe.cheap_score,
            fair_score=scoring.forward_pe.fair_score,
            expensive_score=scoring.forward_pe.expensive_score,
            post_expensive_pe_step=scoring.forward_pe.post_expensive_pe_step,
            post_expensive_score_decay=scoring.forward_pe.post_expensive_score_decay,
            neutral_score=neutral,
        )

        # ── Axis 2: analyst consensus ────────────────────────────────────────
        analyst_score, analyst_present = score_analyst(
            ctx,
            buy_score_max_points=scoring.analyst.buy_score_max_points,
            upside_score_max_points=scoring.analyst.upside_score_max_points,
            upside_cap_pct=scoring.analyst.upside_cap_pct,
            neutral_score=neutral,
        )

        # ── Axis 3: insider net-buy direction ────────────────────────────────
        insider_score, insider_present = score_insider_activity(ctx, neutral_score=neutral)

        # ── Axis 4: generic seasonality (CAPPED) ─────────────────────────────
        seasonality_score, seasonality_present = score_seasonality(
            ctx,
            tailwind_min_avg_return_pct=scoring.seasonality.tailwind_min_avg_return_pct,
            tailwind_min_win_rate_pct=scoring.seasonality.tailwind_min_win_rate_pct,
            headwind_max_avg_return_pct=scoring.seasonality.headwind_max_avg_return_pct,
            headwind_max_win_rate_pct=scoring.seasonality.headwind_max_win_rate_pct,
            neutral_score=neutral,
        )

        # ── Deferred axes: recorded so Phase I knows they exist ──────────────
        unavailable.append("earnings_trend:deferred_no_producer")
        unavailable.append("event_alpha:deferred_no_data_source")

        # ── Assemble present axes with their aggregation weights ─────────────
        present_axes: list[str] = []
        weighted: list[tuple[float, float]] = []  # (score, weight)

        if valuation_present:
            present_axes.append("valuation")
            weighted.append((valuation_score, cfg.valuation_weight))
        else:
            unavailable.append("valuation:no_forward_pe")

        if analyst_present:
            present_axes.append("analyst")
            weighted.append((analyst_score, cfg.analyst_weight))
        else:
            unavailable.append("analyst:no_consensus")

        if insider_present:
            present_axes.append("insider")
            weighted.append((insider_score, cfg.insider_weight))
        else:
            unavailable.append("insider:no_transactions")

        if seasonality_present:
            present_axes.append("seasonality")
            weighted.append((seasonality_score, cfg.seasonality_weight))
        else:
            unavailable.append("seasonality:insufficient_history")

        # ── Coverage-weighted, seasonality-capped aggregate over PRESENT axes ─
        denom = cfg.scored_axis_count if cfg.scored_axis_count > 0 else 1
        coverage_score = min(1.0, len(present_axes) / denom)

        aggregate_score: float | None = None
        if weighted:
            weight_sum = sum(w for _, w in weighted)
            if weight_sum > 0:
                aggregate_score = sum(s * w for s, w in weighted) / weight_sum
                aggregate_score = max(0.0, min(100.0, aggregate_score))
                reasons.append(
                    f"aggregate from {len(present_axes)} axes: {', '.join(present_axes)}"
                )

        metadata: dict[str, Any] = {
            "axis_scores": {
                "valuation": round(valuation_score, 4) if valuation_present else None,
                "analyst": round(analyst_score, 4) if analyst_present else None,
                "insider": round(insider_score, 4) if insider_present else None,
                "seasonality": (round(seasonality_score, 4) if seasonality_present else None),
            },
            "axis_weights": {
                "valuation": cfg.valuation_weight,
                "analyst": cfg.analyst_weight,
                "insider": cfg.insider_weight,
                "seasonality": cfg.seasonality_weight,
            },
            "scored_axis_count": cfg.scored_axis_count,
        }

        return CompanyQualityContextEvidence(
            valuation_score=valuation_score if valuation_present else None,
            earnings_trend_score=None,
            analyst_score=analyst_score if analyst_present else None,
            insider_score=insider_score if insider_present else None,
            seasonality_score=seasonality_score if seasonality_present else None,
            present_axes=tuple(present_axes),
            aggregate_score=aggregate_score,
            coverage_score=coverage_score,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=tuple(reasons),
            unavailable_reasons=tuple(unavailable),
            metadata=metadata,
        )
