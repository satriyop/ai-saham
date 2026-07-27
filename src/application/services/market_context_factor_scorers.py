"""
Market context factor scoring — pure functions, no state, no IO.

Each score_* function maps raw candle/series data plus config thresholds to a
ContextFactor (score 0.0-1.0, label, rationale). Used by BuildMarketContextUseCase.

Layer: Application
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.config.market_context_config import ScoreLabelThresholds
from src.application.services.stats import interpolate
from src.domain.entities.candle import Candle
from src.domain.value_objects.market_context import ContextFactor, MarketRegime


def score_vix(
    cfg,
    candles: list[Candle],
    as_of: date,
    labels: ScoreLabelThresholds,
) -> ContextFactor:
    if not cfg.enabled:
        return disabled_context_factor("vix", cfg.weight)
    close = latest_close(candles)
    if close is None:
        return unavailable_context_factor(
            "vix",
            cfg.weight,
            f"no {cfg.ticker} candles cached; run: saham fetch market {cfg.ticker}",
        )

    v = float(close)
    if v <= cfg.very_low:
        score = cfg.very_low_score
    elif v <= cfg.low:
        score = _interpolate_score(v, cfg.very_low, cfg.low, cfg.very_low_score, cfg.low_score)
    elif v <= cfg.elevated:
        score = _interpolate_score(v, cfg.low, cfg.elevated, cfg.low_score, cfg.elevated_score)
    elif v < cfg.high:
        score = _interpolate_score(
            v,
            cfg.elevated,
            cfg.high,
            cfg.elevated_score,
            cfg.risk_off_score,
        )
    else:  # v >= cfg.high → score 0.0; VOLATILE override fires separately
        score = cfg.high_score
    label = _score_label(score, labels)

    rationale = f"VIX {v:.1f}"
    if v <= cfg.very_low:
        rationale += f" (very low ≤{cfg.very_low})"
    elif v <= cfg.low:
        rationale += f" (low {cfg.very_low}–{cfg.low})"
    elif v <= cfg.elevated:
        rationale += f" (elevated {cfg.low}–{cfg.elevated})"
    elif v < cfg.high:
        rationale += f" (risk_off {cfg.elevated}–{cfg.high})"
    else:
        rationale += f" (volatile ≥{cfg.high})"

    return ContextFactor(
        name="vix",
        enabled=True,
        value=v,
        score=round(score, 4),
        weight=cfg.weight,
        label=label,
        rationale=rationale,
    )


def score_eido(
    cfg,
    eido_candles: list[Candle],
    ihsg_candles: list[Candle],
    as_of: date,
    labels: ScoreLabelThresholds,
    neutral_score: float,
) -> ContextFactor:
    if not cfg.enabled:
        return disabled_context_factor("eido", cfg.weight)

    eido_ret = pct_return(eido_candles, cfg.lookback_days)
    ihsg_ret = pct_return(ihsg_candles, cfg.lookback_days)

    if eido_ret is None:
        return unavailable_context_factor(
            "eido",
            cfg.weight,
            f"no {cfg.ticker} candles cached; run: saham fetch market {cfg.ticker}",
        )

    if ihsg_ret is None:
        # Fall back to absolute EIDO return vs zero
        divergence = eido_ret
        rationale_suffix = f"EIDO {eido_ret:+.1f}% (no IHSG data for divergence)"
    else:
        divergence = eido_ret - ihsg_ret
        rationale_suffix = (
            f"EIDO {eido_ret:+.1f}% vs IHSG {ihsg_ret:+.1f}% "
            f"({cfg.lookback_days}d, divergence {divergence:+.1f}%)"
        )

    score = _piecewise_linear(divergence, cfg.discount_pct, cfg.premium_pct, neutral_score)
    label = _score_label(score, labels)

    return ContextFactor(
        name="eido",
        enabled=True,
        value=round(divergence, 4),
        score=round(score, 4),
        weight=cfg.weight,
        label=label,
        rationale=rationale_suffix,
    )


def score_usd_idr(
    cfg,
    candles: list[Candle],
    as_of: date,
    labels: ScoreLabelThresholds,
    neutral_score: float,
) -> ContextFactor:
    if not cfg.enabled:
        return disabled_context_factor("usd_idr", cfg.weight)

    ret = pct_return(candles, cfg.lookback_days)
    if ret is None:
        return unavailable_context_factor(
            "usd_idr",
            cfg.weight,
            f"no {cfg.ticker} candles cached; run: saham fetch market {cfg.ticker}",
        )

    # USD/IDR rises = Rupiah weakens = bearish for IDX
    # So invert: weaken_pct (positive) → score 0.0, strengthen_pct (negative) → score 1.0
    score = _piecewise_linear(ret, cfg.weaken_pct, cfg.strengthen_pct, neutral_score)
    label = _score_label(score, labels)

    direction = "strengthened" if ret < 0 else "weakened"
    rationale = f"IDR {direction} {abs(ret):.1f}% over {cfg.lookback_days}d (USD/IDR Δ {ret:+.1f}%)"

    return ContextFactor(
        name="usd_idr",
        enabled=True,
        value=round(ret, 4),
        score=round(score, 4),
        weight=cfg.weight,
        label=label,
        rationale=rationale,
    )


def score_idx_trend(
    cfg,
    candles: list[Candle],
    as_of: date,
    labels: ScoreLabelThresholds,
    neutral_score: float,
) -> ContextFactor:
    if not cfg.enabled:
        return disabled_context_factor("idx_trend", cfg.weight)
    if not candles:
        return unavailable_context_factor(
            "idx_trend",
            cfg.weight,
            f"no {cfg.benchmark_ticker} candles cached; "
            f"run: saham fetch market {cfg.benchmark_ticker}",
        )

    close = float(candles[-1].close)
    sma50 = simple_moving_average(candles, cfg.sma_slow)
    sma20 = simple_moving_average(candles, cfg.sma_fast)

    if sma50 is None:
        return unavailable_context_factor(
            "idx_trend",
            cfg.weight,
            f"insufficient history for SMA{cfg.sma_slow}",
        )

    # Primary: % distance from SMA50
    dist_pct = (close - float(sma50)) / float(sma50) * 100.0
    primary_score = _piecewise_linear(
        dist_pct,
        cfg.below_pct_strong,
        cfg.above_pct_strong,
        neutral_score,
    )

    # Secondary: above/below SMA20 (adds 0–0.1 adjustment)
    if sma20 is not None:
        above_fast = close > float(sma20)
        adjustment = cfg.fast_sma_adjustment if above_fast else -cfg.fast_sma_adjustment
        primary_score = min(1.0, primary_score + adjustment)

    score = max(0.0, min(1.0, primary_score))
    label = _score_label(score, labels)

    sma50_str = f"{float(sma50):,.0f}"
    rationale = f"IHSG {close:,.0f} / SMA{cfg.sma_slow} {sma50_str} ({dist_pct:+.1f}%)"
    if sma20 is not None:
        rationale += f" / SMA{cfg.sma_fast} {'above' if close > float(sma20) else 'below'}"

    return ContextFactor(
        name="idx_trend",
        enabled=True,
        value=round(dist_pct, 4),
        score=round(score, 4),
        weight=cfg.weight,
        label=label,
        rationale=rationale,
    )


def score_foreign_flow(
    cfg,
    series: list[tuple[date, Decimal]],
    as_of: date,
    labels: ScoreLabelThresholds,
    neutral_score: float,
) -> ContextFactor:
    if not cfg.enabled:
        return disabled_context_factor("foreign_flow", cfg.weight)
    if not series:
        return unavailable_context_factor(
            "foreign_flow",
            cfg.weight,
            "no broker summary data; run: saham fetch market",
        )

    # Sort by date, take up to reference_days entries
    sorted_series = sorted(series, key=lambda x: x[0])
    lookback = sorted_series[-cfg.lookback_days :]
    reference = (
        sorted_series[-cfg.reference_days :]
        if len(sorted_series) >= cfg.reference_days
        else sorted_series
    )

    if not lookback:
        return unavailable_context_factor("foreign_flow", cfg.weight, "insufficient broker data")

    recent_avg = sum(v for _, v in lookback) / len(lookback)
    ref_avg = sum(v for _, v in reference) / len(reference) if reference else Decimal("0")

    # Score: compare recent_avg to ref_avg
    # recent_avg > ref_avg → more bullish than baseline → score > 0.5
    # recent_avg == ref_avg → score = 0.5
    # Use ratio of difference vs |ref_avg| to normalize, fallback to sign if ref=0
    if ref_avg == 0:
        score = 1.0 if recent_avg > 0 else (neutral_score if recent_avg == 0 else 0.0)
    else:
        # diff as % of abs(ref_avg): +50% diff → score 1.0; -50% diff → score 0.0
        diff_ratio = float((recent_avg - ref_avg) / abs(ref_avg))
        score = _piecewise_linear(
            diff_ratio,
            cfg.bearish_diff_ratio,
            cfg.bullish_diff_ratio,
            neutral_score,
        )

    label = _score_label(score, labels)
    flow_str = _fmt_idr(recent_avg)
    ref_str = _fmt_idr(ref_avg)
    rationale = (
        f"Net foreign {flow_str} avg/{cfg.lookback_days}d (ref {ref_str} avg/{cfg.reference_days}d)"
    )

    return ContextFactor(
        name="foreign_flow",
        enabled=True,
        value=round(float(recent_avg), 2),
        score=round(score, 4),
        weight=cfg.weight,
        label=label,
        rationale=rationale,
    )


def score_idx_breadth(
    cfg,
    universe_candles: dict[str, list[Candle]],
    as_of: date,
    labels: ScoreLabelThresholds,
    neutral_score: float,
) -> ContextFactor:
    if not cfg.enabled:
        return disabled_context_factor("idx_breadth", cfg.weight)
    if not universe_candles:
        return unavailable_context_factor("idx_breadth", cfg.weight, "no universe candles provided")

    period = cfg.above_sma_period
    evaluated = 0
    above = 0
    for ticker, candles in universe_candles.items():
        if len(candles) < period:
            continue
        sma = simple_moving_average(candles, period)
        if sma is None or sma <= 0:
            continue
        evaluated += 1
        if candles[-1].close > sma:
            above += 1

    if evaluated == 0:
        return unavailable_context_factor(
            "idx_breadth",
            cfg.weight,
            "no tickers with sufficient history",
        )

    breadth_pct = above / evaluated * 100.0
    score = _piecewise_linear(breadth_pct, cfg.bearish_pct, cfg.bullish_pct, neutral_score)
    label = _score_label(score, labels)
    rationale = (
        f"{breadth_pct:.1f}% of {evaluated} tickers above SMA{period} "
        f"(bearish <{cfg.bearish_pct}%, bullish >{cfg.bullish_pct}%)"
    )

    return ContextFactor(
        name="idx_breadth",
        enabled=True,
        value=round(breadth_pct, 4),
        score=round(score, 4),
        weight=cfg.weight,
        label=label,
        rationale=rationale,
    )


def weighted_market_conviction(factors: list[ContextFactor], neutral_score: float) -> float:
    """Weighted average of available scores; renormalizes when factors are skipped."""
    active = [(f.score, f.weight) for f in factors if f.score is not None]
    if not active:
        return neutral_score
    total_weight = sum(w for _, w in active)
    if total_weight == 0:
        return neutral_score
    return sum(s * w for s, w in active) / total_weight


def classify_market_regime(
    conviction: float,
    vix_close: Decimal | None,
    thresholds,
) -> MarketRegime:
    # VOLATILE override: VIX hard threshold takes precedence
    if vix_close is not None and float(vix_close) > thresholds.volatile_vix_override:
        return MarketRegime.VOLATILE
    if conviction >= thresholds.risk_on_min_score:
        return MarketRegime.RISK_ON
    if conviction <= thresholds.risk_off_max_score:
        return MarketRegime.RISK_OFF
    return MarketRegime.NEUTRAL


def latest_close(candles: list[Candle]) -> Decimal | None:
    return candles[-1].close if candles else None


def pct_return(candles: list[Candle], periods: int) -> float | None:
    if len(candles) <= periods:
        return None
    latest = candles[-1].close
    prior = candles[-(periods + 1)].close
    if prior <= 0:
        return None
    return float((latest - prior) / prior * 100)


def simple_moving_average(candles: list[Candle], period: int) -> Decimal | None:
    if len(candles) < period:
        return None
    closes = [c.close for c in candles[-period:]]
    return sum(closes, Decimal("0")) / Decimal(period)


def unavailable_context_factor(name: str, weight: float, reason: str) -> ContextFactor:
    return ContextFactor(
        name=name,
        enabled=True,
        value=None,
        score=None,
        weight=weight,
        label="UNAVAILABLE",
        rationale=reason,
    )


def disabled_context_factor(name: str, weight: float) -> ContextFactor:
    return ContextFactor(
        name=name,
        enabled=False,
        value=None,
        score=None,
        weight=weight,
        label="DISABLED",
        rationale="disabled in config",
    )


# ── Private helpers ─────────────────────────────────────────────────────────


def _piecewise_linear(value: float, low: float, high: float, neutral_score: float = 0.5) -> float:
    """Map value linearly from low→0.0 to high→1.0, clamped."""
    if high == low:
        return neutral_score
    ratio = (value - low) / (high - low)
    return max(0.0, min(1.0, ratio))


def _interpolate_score(
    value: float,
    low_value: float,
    high_value: float,
    low_score: float,
    high_score: float,
) -> float:
    return interpolate(value, low_value, high_value, low_score, high_score)


def _score_label(score: float, labels: ScoreLabelThresholds) -> str:
    if score >= labels.favorable_min_score:
        return "FAVORABLE"
    if score >= labels.neutral_min_score:
        return "NEUTRAL"
    return "STRESSED"


def _fmt_idr(value: Decimal) -> str:
    """Format a net foreign flow value as a compact Rupiah string (e.g. +Rp 312.4B)."""
    v = float(value)
    sign = "+" if v >= 0 else "-"
    abs_v = abs(v)
    if abs_v >= 1_000_000_000_000:
        return f"{sign}Rp {abs_v / 1_000_000_000_000:.1f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}Rp {abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}Rp {abs_v / 1_000_000:.1f}M"
    return f"{sign}Rp {abs_v:.0f}"
