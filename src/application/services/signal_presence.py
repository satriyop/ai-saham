"""Shared SignalContext presence rules for audit and evidence annotation."""

from __future__ import annotations

from src.domain.value_objects.signal_assessment import SignalContext

MIN_SEASONALITY_YEARS = 5


def has_usable_seasonality(ctx: SignalContext) -> bool:
    """Return True only when seasonality has values and a known 5y+ sample."""
    return (
        ctx.seasonality_win_rate is not None
        and ctx.seasonality_avg_return_pct is not None
        and ctx.seasonality_total_years is not None
        and ctx.seasonality_total_years >= MIN_SEASONALITY_YEARS
    )


def is_signal_factor_present(factor: str, ctx: SignalContext) -> bool:
    """Canonical per-factor presence rule used by audit/evidence paths."""
    if factor == "bandar_intensity":
        return ctx.bandar_broad_score is not None
    if factor == "foreign_flow_quality":
        return ctx.foreign_flow_quality is not None
    if factor == "insider_activity":
        return ctx.insider_net_buy_ratio is not None
    if factor == "seasonality_edge":
        return has_usable_seasonality(ctx)
    if factor == "analyst_consensus":
        return ctx.analyst_buy_pct is not None
    if factor == "forward_valuation":
        return ctx.forward_pe is not None and ctx.forward_pe > 0
    return False
