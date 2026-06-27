"""
BuildMarketContextUseCase — deterministic cross-market regime computation.

Pure computation: no repository, no providers, no IO. Receives pre-loaded
candle data from MarketContextEngine and scores each factor 0.0–1.0.
Renormalizes weights when factors are disabled or data is unavailable.

Factors (Phase 1): vix, eido, usd_idr, idx_trend, idx_breadth
Factors (Phase 2): foreign_flow
Factors (optional): commodity_composite

Layer: Application
Depends on: Domain only (market_context, Candle entity, MarketContextConfig)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.domain.entities.candle import Candle
from src.domain.value_objects.market_context import (
    ContextFactor,
    MarketContext,
    MarketRegime,
)
from src.infrastructure.config.market_context_config import MarketContextConfig
from src.infrastructure.config.market_context_config import ScoreLabelThresholds


@dataclass
class BuildMarketContextRequest:
    """Pre-loaded data for all factors. Empty list = data unavailable (skipped)."""

    config: MarketContextConfig
    as_of_date: date

    # Cross-market (fetched by MarketContextEngine via YahooFinanceProvider)
    vix_candles: list[Candle]
    eido_candles: list[Candle]
    ihsg_candles: list[Candle]    # used by both eido and idx_trend
    usd_idr_candles: list[Candle]

    # IDX-internal breadth (fetched from MarketDataRepository per universe ticker)
    universe_candles: dict[str, list[Candle]]  # ticker → candle history

    # Foreign flow: list of (date, net_value) tuples, aggregated across universe by engine.
    # Each tuple = one trading day's total net foreign value across all universe tickers.
    foreign_flow_series: list[tuple[date, Decimal]] = field(default_factory=list)


@dataclass
class BuildMarketContextResponse:
    context: MarketContext


class BuildMarketContextUseCase:
    """
    Pure computation: no state, no IO.

    Called by MarketContextEngine after it fetches all raw data.
    Each factor scorer returns (score | None, raw_value | None, rationale).
    Missing scores are excluded from the weighted average; remaining weights renormalize.
    """

    def execute(self, request: BuildMarketContextRequest) -> BuildMarketContextResponse:
        cfg = request.config
        as_of = request.as_of_date

        factors: list[ContextFactor] = []

        # ── VIX ──────────────────────────────────────────────────────────────
        factors.append(self._score_vix(cfg.vix, request.vix_candles, as_of, cfg.scoring.labels))

        # ── EIDO ─────────────────────────────────────────────────────────────
        factors.append(self._score_eido(
            cfg.eido, request.eido_candles, request.ihsg_candles, as_of,
            cfg.scoring.labels, cfg.scoring.neutral_score,
        ))

        # ── USD/IDR ──────────────────────────────────────────────────────────
        factors.append(self._score_usd_idr(
            cfg.usd_idr, request.usd_idr_candles, as_of,
            cfg.scoring.labels, cfg.scoring.neutral_score,
        ))

        # ── IDX Trend ────────────────────────────────────────────────────────
        factors.append(self._score_idx_trend(
            cfg.idx_trend, request.ihsg_candles, as_of,
            cfg.scoring.labels, cfg.scoring.neutral_score,
        ))

        # ── IDX Breadth ──────────────────────────────────────────────────────
        factors.append(self._score_idx_breadth(
            cfg.idx_breadth, request.universe_candles, as_of,
            cfg.scoring.labels, cfg.scoring.neutral_score,
        ))

        # ── Foreign Flow ─────────────────────────────────────────────────────
        factors.append(self._score_foreign_flow(
            cfg.foreign_flow, request.foreign_flow_series, as_of,
            cfg.scoring.labels, cfg.scoring.neutral_score,
        ))

        # ── Commodity Composite (optional) ────────────────────────────────────
        if cfg.commodity.enabled:
            factors.append(_unavailable("commodity_composite", cfg.commodity.weight, "commodity data not yet fetched"))
        else:
            factors.append(_disabled("commodity_composite", cfg.commodity.weight))

        # ── Aggregate ────────────────────────────────────────────────────────
        conviction = _weighted_conviction(factors, cfg.scoring.neutral_score)
        vix_value = _latest_close(request.vix_candles)
        regime = _classify_regime(conviction, vix_value, cfg.regime_thresholds)
        effect = cfg.get_effect(regime.value)

        staleness = _staleness_warning(
            request.vix_candles,
            request.eido_candles,
            request.usd_idr_candles,
            as_of,
            cfg.scoring.stale_business_day_gap,
        )
        coverage = _coverage_warning(factors, cfg.scoring.coverage_warning_unavailable_ratio)

        context = MarketContext(
            regime=regime,
            conviction=round(conviction, 4),
            factors=tuple(factors),
            signal_multiplier=effect.signal_multiplier,
            gate_tightening=effect.gate_tightening,
            as_of_date=as_of,
            staleness_warning=staleness,
            coverage_warning=coverage,
        )
        return BuildMarketContextResponse(context=context)

    # ── Factor scorers ────────────────────────────────────────────────────────

    def _score_vix(
        self,
        cfg,
        candles: list[Candle],
        as_of: date,
        labels: ScoreLabelThresholds,
    ) -> ContextFactor:
        if not cfg.enabled:
            return _disabled("vix", cfg.weight)
        close = _latest_close(candles)
        if close is None:
            return _unavailable("vix", cfg.weight, f"no {cfg.ticker} candles cached; run: saham fetch market {cfg.ticker}")

        v = float(close)
        if v <= cfg.very_low:
            score = cfg.very_low_score
        elif v <= cfg.low:
            score = _interpolate_score(
                v, cfg.very_low, cfg.low, cfg.very_low_score, cfg.low_score
            )
        elif v <= cfg.elevated:
            score = _interpolate_score(
                v, cfg.low, cfg.elevated, cfg.low_score, cfg.elevated_score
            )
        elif v < cfg.high:
            score = _interpolate_score(
                v, cfg.elevated, cfg.high, cfg.elevated_score, cfg.risk_off_score
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

        return ContextFactor(name="vix", enabled=True, value=v, score=round(score, 4),
                             weight=cfg.weight, label=label, rationale=rationale)

    def _score_eido(
        self,
        cfg,
        eido_candles: list[Candle],
        ihsg_candles: list[Candle],
        as_of: date,
        labels: ScoreLabelThresholds,
        neutral_score: float,
    ) -> ContextFactor:
        if not cfg.enabled:
            return _disabled("eido", cfg.weight)

        eido_ret = _pct_return(eido_candles, cfg.lookback_days)
        ihsg_ret = _pct_return(ihsg_candles, cfg.lookback_days)

        if eido_ret is None:
            return _unavailable("eido", cfg.weight, f"no {cfg.ticker} candles cached; run: saham fetch market {cfg.ticker}")

        if ihsg_ret is None:
            # Fall back to absolute EIDO return vs zero
            divergence = eido_ret
            rationale_suffix = f"EIDO {eido_ret:+.1f}% (no IHSG data for divergence)"
        else:
            divergence = eido_ret - ihsg_ret
            rationale_suffix = f"EIDO {eido_ret:+.1f}% vs IHSG {ihsg_ret:+.1f}% ({cfg.lookback_days}d, divergence {divergence:+.1f}%)"

        score = _piecewise_linear(divergence, cfg.discount_pct, cfg.premium_pct, neutral_score)
        label = _score_label(score, labels)

        return ContextFactor(name="eido", enabled=True, value=round(divergence, 4), score=round(score, 4),
                             weight=cfg.weight, label=label, rationale=rationale_suffix)

    def _score_usd_idr(
        self,
        cfg,
        candles: list[Candle],
        as_of: date,
        labels: ScoreLabelThresholds,
        neutral_score: float,
    ) -> ContextFactor:
        if not cfg.enabled:
            return _disabled("usd_idr", cfg.weight)

        ret = _pct_return(candles, cfg.lookback_days)
        if ret is None:
            return _unavailable("usd_idr", cfg.weight, f"no {cfg.ticker} candles cached; run: saham fetch market {cfg.ticker}")

        # USD/IDR rises = Rupiah weakens = bearish for IDX
        # So invert: weaken_pct (positive) → score 0.0, strengthen_pct (negative) → score 1.0
        score = _piecewise_linear(ret, cfg.weaken_pct, cfg.strengthen_pct, neutral_score)
        label = _score_label(score, labels)

        direction = "strengthened" if ret < 0 else "weakened"
        rationale = f"IDR {direction} {abs(ret):.1f}% over {cfg.lookback_days}d (USD/IDR Δ {ret:+.1f}%)"

        return ContextFactor(name="usd_idr", enabled=True, value=round(ret, 4), score=round(score, 4),
                             weight=cfg.weight, label=label, rationale=rationale)

    def _score_idx_trend(
        self,
        cfg,
        candles: list[Candle],
        as_of: date,
        labels: ScoreLabelThresholds,
        neutral_score: float,
    ) -> ContextFactor:
        if not cfg.enabled:
            return _disabled("idx_trend", cfg.weight)
        if not candles:
            return _unavailable("idx_trend", cfg.weight, f"no {cfg.benchmark_ticker} candles cached; run: saham fetch market {cfg.benchmark_ticker}")

        close = float(candles[-1].close)
        sma50 = _sma(candles, cfg.sma_slow)
        sma20 = _sma(candles, cfg.sma_fast)

        if sma50 is None:
            return _unavailable("idx_trend", cfg.weight, f"insufficient history for SMA{cfg.sma_slow}")

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

        return ContextFactor(name="idx_trend", enabled=True, value=round(dist_pct, 4), score=round(score, 4),
                             weight=cfg.weight, label=label, rationale=rationale)

    def _score_foreign_flow(
        self,
        cfg,
        series: list[tuple[date, Decimal]],
        as_of: date,
        labels: ScoreLabelThresholds,
        neutral_score: float,
    ) -> ContextFactor:
        if not cfg.enabled:
            return _disabled("foreign_flow", cfg.weight)
        if not series:
            return _unavailable("foreign_flow", cfg.weight, "no broker summary data; run: saham fetch market")

        # Sort by date, take up to reference_days entries
        sorted_series = sorted(series, key=lambda x: x[0])
        lookback = sorted_series[-cfg.lookback_days:]
        reference = sorted_series[-cfg.reference_days:] if len(sorted_series) >= cfg.reference_days else sorted_series

        if not lookback:
            return _unavailable("foreign_flow", cfg.weight, "insufficient broker data")

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
        rationale = f"Net foreign {flow_str} avg/{cfg.lookback_days}d (ref {ref_str} avg/{cfg.reference_days}d)"

        return ContextFactor(name="foreign_flow", enabled=True, value=round(float(recent_avg), 2),
                             score=round(score, 4), weight=cfg.weight, label=label, rationale=rationale)

    def _score_idx_breadth(
        self,
        cfg,
        universe_candles: dict[str, list[Candle]],
        as_of: date,
        labels: ScoreLabelThresholds,
        neutral_score: float,
    ) -> ContextFactor:
        if not cfg.enabled:
            return _disabled("idx_breadth", cfg.weight)
        if not universe_candles:
            return _unavailable("idx_breadth", cfg.weight, "no universe candles provided")

        period = cfg.above_sma_period
        evaluated = 0
        above = 0
        for ticker, candles in universe_candles.items():
            if len(candles) < period:
                continue
            sma = _sma(candles, period)
            if sma is None or sma <= 0:
                continue
            evaluated += 1
            if candles[-1].close > sma:
                above += 1

        if evaluated == 0:
            return _unavailable("idx_breadth", cfg.weight, "no tickers with sufficient history")

        breadth_pct = above / evaluated * 100.0
        score = _piecewise_linear(breadth_pct, cfg.bearish_pct, cfg.bullish_pct, neutral_score)
        label = _score_label(score, labels)
        rationale = f"{breadth_pct:.1f}% of {evaluated} tickers above SMA{period} (bearish <{cfg.bearish_pct}%, bullish >{cfg.bullish_pct}%)"

        return ContextFactor(name="idx_breadth", enabled=True, value=round(breadth_pct, 4), score=round(score, 4),
                             weight=cfg.weight, label=label, rationale=rationale)


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    if high_value == low_value:
        return high_score
    progress = (value - low_value) / (high_value - low_value)
    return low_score + progress * (high_score - low_score)


def _score_label(score: float, labels: ScoreLabelThresholds) -> str:
    if score >= labels.favorable_min_score:
        return "FAVORABLE"
    if score >= labels.neutral_min_score:
        return "NEUTRAL"
    return "STRESSED"


def _latest_close(candles: list[Candle]) -> Decimal | None:
    return candles[-1].close if candles else None


def _pct_return(candles: list[Candle], periods: int) -> float | None:
    if len(candles) <= periods:
        return None
    latest = candles[-1].close
    prior = candles[-(periods + 1)].close
    if prior <= 0:
        return None
    return float((latest - prior) / prior * 100)


def _sma(candles: list[Candle], period: int) -> Decimal | None:
    if len(candles) < period:
        return None
    closes = [c.close for c in candles[-period:]]
    return sum(closes, Decimal("0")) / Decimal(period)


def _weighted_conviction(factors: list[ContextFactor], neutral_score: float) -> float:
    """Weighted average of available scores; renormalizes when factors are skipped."""
    active = [(f.score, f.weight) for f in factors if f.score is not None]
    if not active:
        return neutral_score
    total_weight = sum(w for _, w in active)
    if total_weight == 0:
        return neutral_score
    return sum(s * w for s, w in active) / total_weight


def _classify_regime(conviction: float, vix_close: Decimal | None, thresholds) -> MarketRegime:
    # VOLATILE override: VIX hard threshold takes precedence
    if vix_close is not None and float(vix_close) > thresholds.volatile_vix_override:
        return MarketRegime.VOLATILE
    if conviction >= thresholds.risk_on_min_score:
        return MarketRegime.RISK_ON
    if conviction <= thresholds.risk_off_max_score:
        return MarketRegime.RISK_OFF
    return MarketRegime.NEUTRAL


def _business_day_gap(start: date, end: date) -> int:
    """Count weekday-only days between start (exclusive) and end (inclusive)."""
    days, current = 0, start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:  # Mon–Fri
            days += 1
        current += timedelta(days=1)
    return days


def _staleness_warning(
    vix_candles: list[Candle],
    eido_candles: list[Candle],
    usd_idr_candles: list[Candle],
    as_of: date,
    stale_business_day_gap: int,
) -> str | None:
    stale = []
    for name, candles in [("VIX", vix_candles), ("EIDO", eido_candles), ("USD/IDR", usd_idr_candles)]:
        if candles and _business_day_gap(candles[-1].date, as_of) > stale_business_day_gap:
            stale.append(f"{name} ({candles[-1].date})")
    return f"Using T-1 data for: {', '.join(stale)}. Run: saham fetch market" if stale else None


def _coverage_warning(factors: list[ContextFactor], unavailable_ratio: float) -> str | None:
    enabled = [f for f in factors if f.enabled]
    unavailable = [f for f in enabled if f.score is None]
    if enabled and len(unavailable) / len(enabled) >= unavailable_ratio:
        names = ", ".join(f.name for f in unavailable)
        return f"{len(unavailable)}/{len(enabled)} factors unavailable: {names}"
    return None


def _disabled(name: str, weight: float) -> ContextFactor:
    return ContextFactor(name=name, enabled=False, value=None, score=None,
                         weight=weight, label="DISABLED", rationale="disabled in config")


def _unavailable(name: str, weight: float, reason: str) -> ContextFactor:
    return ContextFactor(name=name, enabled=True, value=None, score=None,
                         weight=weight, label="UNAVAILABLE", rationale=reason)


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
