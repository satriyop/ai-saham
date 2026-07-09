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

from src.application.services.stats import interpolate
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

    # ── A2: regime quality inputs (computed by engine from prior observations) ──
    # Passed in so use case stays pure (no IO).
    days_in_regime: int | None = None       # consecutive days in current regime
    regime_stability: str | None = None     # "STABLE" | "TRANSITIONING" | "UNKNOWN"
    banking_universe: list[str] = field(default_factory=list)  # tickers for banking_sector_vs_ihsg


@dataclass
class BuildMarketContextResponse:
    context: MarketContext
    regime_detection_inputs: dict = field(default_factory=dict)  # raw fingerprint values for A2


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

        # ── A2: regime confidence and detection inputs ────────────────────────
        regime_confidence = _compute_regime_confidence(
            regime=regime,
            conviction=conviction,
            vix_value=vix_value,
            thresholds=cfg.regime_thresholds,
        )

        breadth_factor = next((f for f in factors if f.name == "idx_breadth"), None)
        breadth_pct = breadth_factor.value if breadth_factor and breadth_factor.value is not None else None

        detection_inputs = {
            **_compute_ihsg_inputs(request.ihsg_candles),
            **_compute_foreign_flow_inputs(request.foreign_flow_series),
            "ihsg_breadth_pct_above_ma": round(breadth_pct, 4) if breadth_pct is not None else None,
            "sector_breadth": round(breadth_pct, 4) if breadth_pct is not None else None,
            "banking_sector_vs_ihsg": _compute_banking_vs_ihsg(
                request.banking_universe, request.universe_candles, request.ihsg_candles
            ),
        }

        transition_warning: str | None = None
        if request.regime_stability == "TRANSITIONING":
            transition_warning = f"Regime changed recently — in {regime.value} for {request.days_in_regime or 0} day(s)"

        context = MarketContext(
            regime=regime,
            conviction=round(conviction, 4),
            factors=tuple(factors),
            signal_multiplier=effect.signal_multiplier,
            gate_tightening=effect.gate_tightening,
            as_of_date=as_of,
            staleness_warning=staleness,
            coverage_warning=coverage,
            regime_confidence=round(regime_confidence, 4),
            regime_stability=request.regime_stability,
            days_in_regime=request.days_in_regime,
            transition_warning=transition_warning,
        )
        return BuildMarketContextResponse(context=context, regime_detection_inputs=detection_inputs)

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
    return interpolate(value, low_value, high_value, low_score, high_score)


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
    return f"Using T-1 data for: {', '.join(stale)}. Run: saham fetch market --universe lq45" if stale else None


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


# ── A2: regime confidence and detection input helpers ─────────────────────────

def _compute_regime_confidence(
    *,
    regime: MarketRegime,
    conviction: float,
    vix_value,
    thresholds,
) -> float:
    """
    Compute regime confidence (0.0–1.0) as the conviction margin from the nearest
    regime boundary, normalized to a [0, 1] range.

    VOLATILE confidence is based on VIX distance from the hard threshold.
    """
    risk_on_min  = thresholds.risk_on_min_score
    risk_off_max = thresholds.risk_off_max_score
    # half of the neutral band (risk_off_max ... risk_on_min)
    boundary_half = (risk_on_min - risk_off_max) / 2.0

    if boundary_half <= 0:
        return 0.5

    if regime == MarketRegime.VOLATILE:
        if vix_value is not None:
            vix_v = float(vix_value)
            vt = thresholds.volatile_vix_override
            if vt > 0:
                margin = max(0.0, vix_v - vt) / vt
                return min(1.0, round(margin, 4))
        return 0.8  # hard threshold fired — treat as high confidence

    if regime == MarketRegime.RISK_ON:
        margin = conviction - risk_on_min
    elif regime == MarketRegime.RISK_OFF:
        margin = risk_off_max - conviction
    else:  # NEUTRAL
        margin = min(conviction - risk_off_max, risk_on_min - conviction)

    return min(1.0, max(0.0, round(margin / boundary_half, 4)))


def _compute_ihsg_inputs(candles: list) -> dict:
    """
    Compute IHSG-based detection inputs from raw candle history.

    Returns a dict with keys: ihsg_20d_return, ihsg_trend_structure,
    ihsg_volume_trend, ihsg_atr_pct.  All values are float | None.
    """
    if not candles or len(candles) < 2:
        return {
            "ihsg_20d_return": None,
            "ihsg_trend_structure": None,
            "ihsg_volume_trend": None,
            "ihsg_atr_pct": None,
        }

    ihsg_20d_return = _pct_return(candles, 20)

    # Trend structure: close vs SMA20 vs SMA50
    close = float(candles[-1].close)
    sma20 = _sma(candles, 20)
    sma50 = _sma(candles, 50)

    if sma50 is not None and sma20 is not None:
        above_50 = close >= float(sma50)
        above_20 = close >= float(sma20)
        if above_50 and above_20:
            trend_structure = "ABOVE_BOTH"
        elif above_20 and not above_50:
            trend_structure = "ABOVE_FAST_ONLY"
        else:
            trend_structure = "BELOW_BOTH"
    elif sma20 is not None:
        trend_structure = "ABOVE_FAST_ONLY" if close >= float(sma20) else "BELOW_FAST_ONLY"
    else:
        trend_structure = "UNKNOWN"

    # Volume trend: recent 5d avg vol / 20d avg vol
    volume_trend: float | None = None
    volumes = [
        float(c.volume) for c in candles
        if hasattr(c, "volume") and c.volume is not None and float(c.volume) > 0
    ]
    if len(volumes) >= 20:
        recent_vol = sum(volumes[-5:]) / min(5, len(volumes[-5:]))
        avg_vol    = sum(volumes[-20:]) / 20
        if avg_vol > 0:
            volume_trend = round(recent_vol / avg_vol, 4)

    # IHSG ATR% (14d): average true range / close * 100
    atr_pct: float | None = None
    atr_period = 14
    if len(candles) >= atr_period + 1:
        trs = []
        for i in range(-atr_period, 0):
            c_curr = candles[i]
            c_prev = candles[i - 1]
            high   = float(c_curr.high) if hasattr(c_curr, "high") and c_curr.high else float(c_curr.close)
            low    = float(c_curr.low)  if hasattr(c_curr, "low")  and c_curr.low  else float(c_curr.close)
            prev_c = float(c_prev.close)
            tr = max(high - low, abs(high - prev_c), abs(low - prev_c))
            trs.append(tr)
        if trs and close > 0:
            atr_pct = round(sum(trs) / len(trs) / close * 100, 4)

    return {
        "ihsg_20d_return": round(ihsg_20d_return, 4) if ihsg_20d_return is not None else None,
        "ihsg_trend_structure": trend_structure,
        "ihsg_volume_trend": volume_trend,
        "ihsg_atr_pct": atr_pct,
    }


def _compute_foreign_flow_inputs(series: list[tuple]) -> dict:
    """
    Derive diagnostic foreign-flow fingerprint inputs from the aggregated series.

    Returns idx_foreign_flow_5d, idx_foreign_flow_20d, foreign_buy_streak,
    foreign_sell_streak.  All values are float | int | None.
    """
    if not series:
        return {
            "idx_foreign_flow_5d": None,
            "idx_foreign_flow_20d": None,
            "foreign_buy_streak": None,
            "foreign_sell_streak": None,
        }

    sorted_series = sorted(series, key=lambda x: x[0])
    values = [float(v) for _, v in sorted_series]

    last_5  = values[-5:]  if len(values) >= 5  else values
    last_20 = values[-20:] if len(values) >= 20 else values

    # Count consecutive tail days with same sign (buy or sell streak)
    buy_streak  = 0
    sell_streak = 0
    for v in reversed(values):
        if v > 0:
            if sell_streak > 0:
                break
            buy_streak += 1
        elif v < 0:
            if buy_streak > 0:
                break
            sell_streak += 1
        else:
            break

    return {
        "idx_foreign_flow_5d": round(sum(last_5), 2) if last_5 else None,
        "idx_foreign_flow_20d": round(sum(last_20), 2) if last_20 else None,
        "foreign_buy_streak": buy_streak if buy_streak > 0 else 0,
        "foreign_sell_streak": sell_streak if sell_streak > 0 else 0,
    }


def _compute_banking_vs_ihsg(
    banking_universe: list[str],
    universe_candles: dict[str, list],
    ihsg_candles: list,
    lookback: int = 20,
) -> float | None:
    """
    Equal-weight banking-sector 20d return minus IHSG 20d return.

    Returns None when banking_universe is empty or tickers lack sufficient history.
    """
    if not banking_universe or not universe_candles or not ihsg_candles:
        return None

    ihsg_ret = _pct_return(ihsg_candles, lookback)
    if ihsg_ret is None:
        return None

    returns = []
    for ticker in banking_universe:
        candles = universe_candles.get(ticker.upper())
        if not candles:
            continue
        ret = _pct_return(candles, lookback)
        if ret is not None:
            returns.append(ret)

    if not returns:
        return None

    banking_ret = sum(returns) / len(returns)
    return round(banking_ret - ihsg_ret, 4)
