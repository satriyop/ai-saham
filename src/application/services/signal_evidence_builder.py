"""
SignalEvidenceBuilder — annotates computed factor scores with evidence metadata.

Phase 1 of the SignalEngine refactor. Receives a SignalContext (raw field
values) and the per-factor breakdown already computed by AssessSignalUseCase,
then produces a SignalEvidence bundle of FactorEvidence records.

NO scoring here. This builder never re-implements scoring — it annotates the
component scores it is handed with direction, strength, confidence, freshness,
provenance, and rationale.

Layer: Application
Depends on: domain value objects + stdlib only.
            No provider, repository, or CLI imports.
"""

from __future__ import annotations

from src.domain.value_objects.factor_evidence import (
    Direction,
    FactorEvidence,
    Freshness,
    Horizon,
)
from src.domain.value_objects.signal_assessment import SignalContext
from src.domain.value_objects.signal_evidence import SignalEvidence

# Static per-factor metadata: (group, horizon, source).
_FACTOR_META: dict[str, tuple[str, Horizon, str]] = {
    "bandar_intensity": ("flow_confirmation", Horizon.DAILY, "bandar_detector"),
    "foreign_flow_quality": ("flow_confirmation", Horizon.DAILY, "foreign_flow_points"),
    "insider_activity": ("context", Horizon.QUARTERLY, "insider_cache"),
    "seasonality_edge": ("context", Horizon.MONTHLY, "seasonality_cache"),
    "analyst_consensus": ("context", Horizon.QUARTERLY, "analyst_cache"),
    "forward_valuation": ("context", Horizon.ANNUAL, "forward_estimates_cache"),
}

# Canonical factor order (matches AssessSignalUseCase breakdown order).
_FACTOR_ORDER: tuple[str, ...] = (
    "bandar_intensity",
    "foreign_flow_quality",
    "insider_activity",
    "seasonality_edge",
    "analyst_consensus",
    "forward_valuation",
)

_BULLISH_MIN_SCORE = 60.0
_BEARISH_MAX_SCORE = 40.0


class SignalEvidenceBuilder:
    """Pure computation. No IO. Annotates scores with evidence metadata."""

    def build(
        self,
        context: SignalContext,
        breakdown: tuple[tuple[str, float], ...],
    ) -> SignalEvidence:
        scores = dict(breakdown)

        factors: list[FactorEvidence] = []
        for name in _FACTOR_ORDER:
            group, horizon, source = _FACTOR_META[name]
            present = self._is_present(name, context)
            component_score = float(scores.get(name, 0.0))

            freshness = Freshness.FRESH if present else Freshness.MISSING
            confidence = 1.0 if present else 0.0
            strength = max(0.0, min(1.0, component_score / 100.0))
            direction = self._direction(present, component_score)
            raw_fields = self._raw_fields(name, context, present)
            rationale = self._rationale(name, context, present, component_score)

            factors.append(
                FactorEvidence(
                    name=name,
                    group=group,
                    direction=direction,
                    strength=strength,
                    confidence=confidence,
                    freshness=freshness,
                    horizon=horizon,
                    source=source,
                    rationale=rationale,
                    raw_fields=raw_fields,
                )
            )

        factors_tuple = tuple(factors)
        present_factors = [
            f for f in factors_tuple if f.freshness != Freshness.MISSING
        ]
        aggregate_confidence = (
            sum(f.confidence for f in present_factors) / len(present_factors)
            if present_factors
            else 0.0
        )
        coverage_ratio = len(present_factors) / len(factors_tuple)
        missing_factors = tuple(
            f.name for f in factors_tuple if f.freshness == Freshness.MISSING
        )

        return SignalEvidence(
            ticker=context.ticker,
            snapshot_date=context.snapshot_date,
            factors=factors_tuple,
            aggregate_confidence=aggregate_confidence,
            coverage_ratio=coverage_ratio,
            missing_factors=missing_factors,
        )

    # ── direction ─────────────────────────────────────────────────────────────

    @staticmethod
    def _direction(present: bool, component_score: float) -> Direction:
        # Never fabricate direction from a neutral fill.
        if not present:
            return Direction.NEUTRAL
        if component_score >= _BULLISH_MIN_SCORE:
            return Direction.BULLISH
        if component_score <= _BEARISH_MAX_SCORE:
            return Direction.BEARISH
        return Direction.NEUTRAL

    # ── presence detection (mirrors AuditSignalUseCase) ───────────────────────

    @staticmethod
    def _is_present(factor: str, ctx: SignalContext) -> bool:
        if factor == "bandar_intensity":
            return ctx.bandar_broad_score is not None
        if factor == "foreign_flow_quality":
            return ctx.foreign_flow_quality is not None
        if factor == "insider_activity":
            return ctx.insider_net_buy_ratio is not None
        if factor == "seasonality_edge":
            return (
                ctx.seasonality_win_rate is not None
                and ctx.seasonality_avg_return_pct is not None
            )
        if factor == "analyst_consensus":
            return ctx.analyst_buy_pct is not None
        if factor == "forward_valuation":
            return ctx.forward_pe is not None and ctx.forward_pe > 0
        return False

    # ── raw fields ────────────────────────────────────────────────────────────

    @staticmethod
    def _raw_fields(
        factor: str, ctx: SignalContext, present: bool
    ) -> tuple[tuple[str, str], ...]:
        if not present:
            return ()
        if factor == "bandar_intensity":
            return (
                ("broad_score", str(ctx.bandar_broad_score)),
                ("max_range", str(ctx.bandar_max_range)),
            )
        if factor == "foreign_flow_quality":
            return (("quality_score", f"{ctx.foreign_flow_quality:.3f}"),)
        if factor == "insider_activity":
            return (("net_buy_ratio", f"{ctx.insider_net_buy_ratio:+.3f}"),)
        if factor == "seasonality_edge":
            fields: list[tuple[str, str]] = [
                ("win_rate", f"{ctx.seasonality_win_rate:.0f}"),
                ("avg_return", f"{ctx.seasonality_avg_return_pct:+.1f}"),
            ]
            if ctx.seasonality_total_years is not None:
                fields.append(("total_years", str(ctx.seasonality_total_years)))
            if ctx.seasonality_back_years is not None:
                fields.append(("back_years", str(ctx.seasonality_back_years)))
            return tuple(fields)
        if factor == "analyst_consensus":
            fields = [("buy_pct", f"{ctx.analyst_buy_pct * 100:.0f}")]
            if ctx.analyst_upside_pct is not None:
                fields.append(("upside_pct", f"{ctx.analyst_upside_pct:+.1f}"))
            return tuple(fields)
        if factor == "forward_valuation":
            return (("pe", f"{ctx.forward_pe:.1f}"),)
        return ()

    # ── rationale ─────────────────────────────────────────────────────────────

    @staticmethod
    def _rationale(
        factor: str, ctx: SignalContext, present: bool, component_score: float
    ) -> str:
        if factor == "bandar_intensity":
            if not present:
                return "no bandar data — neutral fill 50.0"
            return (
                f"broad_score={ctx.bandar_broad_score}/{ctx.bandar_max_range} "
                f"→ {component_score:.1f}/100"
            )
        if factor == "foreign_flow_quality":
            if not present:
                return "no foreign flow data — neutral fill 50.0"
            return (
                f"quality={ctx.foreign_flow_quality:.3f} → {component_score:.1f}/100"
            )
        if factor == "insider_activity":
            if not present:
                return "no insider data — neutral fill 50.0"
            return (
                f"net_buy_ratio={ctx.insider_net_buy_ratio:+.3f} "
                f"→ {component_score:.1f}/100"
            )
        if factor == "seasonality_edge":
            if not present:
                return "no seasonality data — neutral fill 50.0"
            win = ctx.seasonality_win_rate
            avg = ctx.seasonality_avg_return_pct
            if avg > 0 and win > 50:
                lean = "tailwind"
            elif avg < 0 and win < 50:
                lean = "headwind"
            else:
                lean = "neutral"
            years = (
                f" ({ctx.seasonality_total_years}y history)"
                if ctx.seasonality_total_years is not None
                else ""
            )
            return f"win_rate={win:.0f}% avg={avg:+.1f}% → {lean}{years}"
        if factor == "analyst_consensus":
            if not present:
                return "no analyst data — neutral fill 50.0"
            upside = (
                f" upside={ctx.analyst_upside_pct:+.1f}%"
                if ctx.analyst_upside_pct is not None
                else ""
            )
            return (
                f"buy_pct={ctx.analyst_buy_pct * 100:.0f}%{upside} "
                f"→ {component_score:.1f}/100"
            )
        if factor == "forward_valuation":
            if not present:
                return "no forward valuation data — neutral fill 50.0"
            return f"pe={ctx.forward_pe:.1f} → {component_score:.1f}/100"
        return ""
