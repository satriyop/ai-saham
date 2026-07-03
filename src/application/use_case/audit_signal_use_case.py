"""
AuditSignalUseCase — Phase 0 observability for the SignalEngine composite score.

Wraps AssessSignalUseCase and produces a SignalAuditReport that exposes, per
factor: presence, raw context value, component score, configured vs. active
weight, and weighted contribution to the composite total. Also computes a
renormalized_score preview (missing factors excluded from the weight pool)
without touching the production scoring path.

Pure computation: no IO, no providers. Callers supply a fully-populated
SignalContext (built by SignalEngine.build_context) and the weight tables.

Layer: Application
Depends on: domain value objects + AssessSignalUseCase only
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.use_case.assess_signal_use_case import (
    AssessSignalRequest,
    AssessSignalUseCase,
    SignalEngineConfig,
)
from src.domain.value_objects.signal_assessment import SignalContext
from src.domain.value_objects.signal_audit import SignalAuditEntry, SignalAuditReport

# Canonical factor order (matches config/signal_engine.yaml `factors` block).
_FACTOR_ORDER: tuple[str, ...] = (
    "bandar_intensity",
    "foreign_flow_quality",
    "insider_activity",
    "seasonality_edge",
    "analyst_consensus",
    "forward_valuation",
)


@dataclass
class AuditSignalRequest:
    ticker: str
    signal_context: SignalContext
    weights: dict[str, float]      # renormalized active weights (from bootstrap)
    raw_weights: dict[str, float]  # raw configured weights (from YAML factors block)
    config: SignalEngineConfig


@dataclass
class AuditSignalResponse:
    report: SignalAuditReport


class AuditSignalUseCase:
    """Pure computation. No IO. Calls AssessSignalUseCase internally."""

    def execute(self, request: AuditSignalRequest) -> AuditSignalResponse:
        ctx = request.signal_context

        use_case = AssessSignalUseCase(weights=request.weights, config=request.config)
        response = use_case.execute(
            AssessSignalRequest(ticker=request.ticker, signal_context=ctx)
        )
        assessment = response.assessment
        breakdown = dict(assessment.breakdown)

        neutral = request.config.missing_data.neutral_score

        # Iterate factors in canonical YAML order; fall back to any extra factors
        # present in the active weight table so nothing is silently dropped.
        factor_names = list(_FACTOR_ORDER)
        for name in request.weights:
            if name not in factor_names:
                factor_names.append(name)

        entries: list[SignalAuditEntry] = []
        for name in factor_names:
            if name not in request.weights:
                continue
            present = self._is_present(name, ctx)
            raw_value = self._raw_value(name, ctx)
            component_score = breakdown.get(name, neutral)
            active_weight = request.weights[name]
            configured_weight = request.raw_weights.get(name, active_weight)
            entries.append(
                SignalAuditEntry(
                    factor=name,
                    present=present,
                    raw_value=raw_value,
                    component_score=component_score,
                    configured_weight=configured_weight,
                    active_weight=active_weight,
                    weighted_contribution=active_weight * component_score,
                )
            )

        factors_present = sum(1 for e in entries if e.present)
        factors_missing = len(entries) - factors_present
        renormalized_score = self._renormalized_score(entries, neutral)

        report = SignalAuditReport(
            ticker=request.ticker,
            snapshot_date=ctx.snapshot_date,
            entries=tuple(entries),
            final_score=assessment.score,
            strength=assessment.strength.value,
            entry_quality=assessment.entry_quality.value,
            coverage_warning=response.coverage_warning,
            factors_present=factors_present,
            factors_missing=factors_missing,
            renormalized_score=renormalized_score,
        )
        return AuditSignalResponse(report=report)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _renormalized_score(
        entries: list[SignalAuditEntry], neutral: float
    ) -> int:
        """Preview score if missing factors were excluded from the weight pool.

        Present factors are re-weighted so their active weights sum to 1.0, then
        their component scores are averaged. When no factor is present, the
        neutral fill is returned (mirrors the all-missing production result).
        """
        present = [e for e in entries if e.present]
        if not present:
            return max(0, min(100, round(neutral)))
        weight_pool = sum(e.active_weight for e in present)
        if weight_pool <= 0:
            return max(0, min(100, round(neutral)))
        total = sum(e.active_weight * e.component_score for e in present) / weight_pool
        return max(0, min(100, round(total)))

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

    @staticmethod
    def _raw_value(factor: str, ctx: SignalContext) -> str:
        if factor == "bandar_intensity":
            if ctx.bandar_broad_score is None:
                return "None"
            return f"broad_score={ctx.bandar_broad_score}/{ctx.bandar_max_range}"
        if factor == "foreign_flow_quality":
            if ctx.foreign_flow_quality is None:
                return "None"
            return f"quality={ctx.foreign_flow_quality:.3f}"
        if factor == "insider_activity":
            if ctx.insider_net_buy_ratio is None:
                return "None"
            return f"net_buy_ratio={ctx.insider_net_buy_ratio:+.2f}"
        if factor == "seasonality_edge":
            if ctx.seasonality_win_rate is None or ctx.seasonality_avg_return_pct is None:
                return "None"
            return (
                f"win_rate={ctx.seasonality_win_rate:.0f}% "
                f"avg={ctx.seasonality_avg_return_pct:+.1f}%"
            )
        if factor == "analyst_consensus":
            if ctx.analyst_buy_pct is None:
                return "None"
            upside = (
                f" upside={ctx.analyst_upside_pct:+.1f}%"
                if ctx.analyst_upside_pct is not None
                else ""
            )
            return f"buy_pct={ctx.analyst_buy_pct * 100:.0f}%{upside}"
        if factor == "forward_valuation":
            if ctx.forward_pe is None:
                return "None"
            return f"pe={ctx.forward_pe:.1f}"
        return "None"
