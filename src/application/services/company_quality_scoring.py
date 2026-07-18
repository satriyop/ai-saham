"""Shared company-quality conviction scorers (single source of truth).

These four pure scorers back CompanyQualityContextEvidenceBuilder, the sole
diagnostic company-quality evidence producer (RETIRE-LEGACY-SIX-FACTOR-BASELINE
removed the flat-factor scorer that formerly duplicated these formulas).

Each function is pure: (SignalContext + config sub-object + neutral_score) →
(score 0-100, present bool). No IO, no providers, no side effects.

Layer: Application
Depends on: domain (SignalContext) + application stats helper only.
"""

from __future__ import annotations

from src.application.services.stats import interpolate
from src.domain.value_objects.signal_assessment import SignalContext


def score_insider_activity(
    ctx: SignalContext,
    *,
    neutral_score: float,
) -> tuple[float, bool]:
    """
    Insider net buy ratio (-1.0 to +1.0) → 0–100.

    -1.0 (full selling) → 0, 0.0 (neutral) → 50, +1.0 (full buying) → 100.
    Returns neutral 50.0 when no insider data is available (no provider yet).
    """
    if ctx.insider_net_buy_ratio is None:
        return neutral_score, False
    return max(0.0, min(100.0, (ctx.insider_net_buy_ratio + 1.0) / 2.0 * 100.0)), True


def score_seasonality(
    ctx: SignalContext,
    *,
    tailwind_min_avg_return_pct: float,
    tailwind_min_win_rate_pct: float,
    headwind_max_avg_return_pct: float,
    headwind_max_win_rate_pct: float,
    neutral_score: float,
) -> tuple[float, bool]:
    """
    Map seasonal win rate to 0–100 with direction awareness.

    Tailwind  (avg_return > 0 AND win_rate > 50): score = win_rate_pct
    Headwind  (avg_return < 0 AND win_rate < 50): score = win_rate_pct
    Neutral   (everything else):                   score = 50

    This is directional for long-candidate attractiveness: a historically
    weak month should reduce the score, not become a strong positive signal.
    """
    if ctx.seasonality_win_rate is None or ctx.seasonality_avg_return_pct is None:
        return neutral_score, False
    if (
        ctx.seasonality_total_years is None
        or ctx.seasonality_total_years < 5
    ):
        return neutral_score, False

    win = ctx.seasonality_win_rate
    avg = ctx.seasonality_avg_return_pct
    is_tailwind = (
        avg > tailwind_min_avg_return_pct
        and win > tailwind_min_win_rate_pct
    )
    is_headwind = (
        avg < headwind_max_avg_return_pct
        and win < headwind_max_win_rate_pct
    )

    if is_tailwind:
        return win, True
    if is_headwind:
        return win, True
    return neutral_score, True


def score_analyst(
    ctx: SignalContext,
    *,
    buy_score_max_points: float,
    upside_score_max_points: float,
    upside_cap_pct: float,
    neutral_score: float,
) -> tuple[float, bool]:
    """
    Analyst consensus: buy% (max 60 pts) + upside capped at 30% (max 40 pts).

    analyst_buy_pct:  0.0–1.0  fraction of buy recommendations
    analyst_upside_pct: percentage, e.g. 15.0 = 15% price target upside
    """
    if ctx.analyst_buy_pct is None:
        return neutral_score, False
    buy_score = ctx.analyst_buy_pct * buy_score_max_points
    upside_score = (
        max(0.0, min(upside_cap_pct, ctx.analyst_upside_pct or 0.0))
        / upside_cap_pct
        * upside_score_max_points
        if upside_cap_pct > 0
        else 0.0
    )
    return min(100.0, buy_score + upside_score), True


def score_forward_pe(
    ctx: SignalContext,
    *,
    very_cheap_pe: float,
    cheap_pe: float,
    fair_pe: float,
    expensive_pe: float,
    very_cheap_score: float,
    cheap_score: float,
    fair_score: float,
    expensive_score: float,
    post_expensive_pe_step: float,
    post_expensive_score_decay: float,
    neutral_score: float,
) -> tuple[float, bool]:
    """
    Forward P/E → 0–100 via smooth linear interpolation across price tiers.

    P/E ≤ 0 (loss-maker / unavailable) → neutral 50
    P/E ≤ 10                            → 95  (very cheap)
    P/E ≤ 15                            → 95→75 linear
    P/E ≤ 20                            → 75→50 linear
    P/E ≤ 30                            → 50→25 linear
    P/E > 30                            → approaches 0
    """
    pe = ctx.forward_pe
    if pe is None or pe <= 0:
        return neutral_score, False

    if pe <= very_cheap_pe:
        fwd = very_cheap_score
    elif pe <= cheap_pe:
        fwd = interpolate(pe, very_cheap_pe, cheap_pe, very_cheap_score, cheap_score)
    elif pe <= fair_pe:
        fwd = interpolate(pe, cheap_pe, fair_pe, cheap_score, fair_score)
    elif pe <= expensive_pe:
        fwd = interpolate(pe, fair_pe, expensive_pe, fair_score, expensive_score)
    else:
        decay = (
            (pe - expensive_pe)
            / post_expensive_pe_step
            * post_expensive_score_decay
            if post_expensive_pe_step > 0
            else expensive_score
        )
        fwd = max(0.0, expensive_score - decay)

    return fwd, True
