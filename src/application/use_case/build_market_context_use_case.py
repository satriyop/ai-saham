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
from datetime import date
from decimal import Decimal

from src.application.config.market_context_config import MarketContextConfig
from src.application.services.market_context_detection_inputs import (
    compute_market_context_detection_inputs,
    compute_regime_confidence,
)
from src.application.services.market_context_factor_scorers import (
    classify_market_regime,
    disabled_context_factor,
    latest_close,
    score_eido,
    score_foreign_flow,
    score_idx_breadth,
    score_idx_trend,
    score_usd_idr,
    score_vix,
    unavailable_context_factor,
    weighted_market_conviction,
)
from src.application.services.market_context_quality_warnings import (
    market_context_coverage_warning,
    market_context_staleness_warning,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.market_context import ContextFactor, MarketContext


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

        factors: list[ContextFactor] = [
            score_vix(cfg.vix, request.vix_candles, as_of, cfg.scoring.labels),
            score_eido(
                cfg.eido, request.eido_candles, request.ihsg_candles, as_of,
                cfg.scoring.labels, cfg.scoring.neutral_score,
            ),
            score_usd_idr(
                cfg.usd_idr, request.usd_idr_candles, as_of,
                cfg.scoring.labels, cfg.scoring.neutral_score,
            ),
            score_idx_trend(
                cfg.idx_trend, request.ihsg_candles, as_of,
                cfg.scoring.labels, cfg.scoring.neutral_score,
            ),
            score_idx_breadth(
                cfg.idx_breadth, request.universe_candles, as_of,
                cfg.scoring.labels, cfg.scoring.neutral_score,
            ),
            score_foreign_flow(
                cfg.foreign_flow, request.foreign_flow_series, as_of,
                cfg.scoring.labels, cfg.scoring.neutral_score,
            ),
        ]

        # ── Commodity Composite (optional) ────────────────────────────────────
        if cfg.commodity.enabled:
            factors.append(unavailable_context_factor(
                "commodity_composite", cfg.commodity.weight, "commodity data not yet fetched",
            ))
        else:
            factors.append(disabled_context_factor("commodity_composite", cfg.commodity.weight))

        # ── Aggregate ────────────────────────────────────────────────────────
        conviction = weighted_market_conviction(factors, cfg.scoring.neutral_score)
        vix_value = latest_close(request.vix_candles)
        regime = classify_market_regime(conviction, vix_value, cfg.regime_thresholds)
        effect = cfg.get_effect(regime.value)

        staleness = market_context_staleness_warning(
            request.vix_candles,
            request.eido_candles,
            request.usd_idr_candles,
            as_of,
            cfg.scoring.stale_business_day_gap,
        )
        coverage = market_context_coverage_warning(
            factors, cfg.scoring.coverage_warning_unavailable_ratio,
        )

        # ── A2: regime confidence and detection inputs ────────────────────────
        regime_confidence = compute_regime_confidence(
            regime=regime,
            conviction=conviction,
            vix_value=vix_value,
            thresholds=cfg.regime_thresholds,
        )

        breadth_factor = next((f for f in factors if f.name == "idx_breadth"), None)
        breadth_pct = (
            breadth_factor.value
            if breadth_factor and breadth_factor.value is not None
            else None
        )

        detection_inputs = compute_market_context_detection_inputs(
            ihsg_candles=request.ihsg_candles,
            foreign_flow_series=request.foreign_flow_series,
            idx_breadth_pct=breadth_pct,
            banking_universe=request.banking_universe,
            universe_candles=request.universe_candles,
        )

        transition_warning: str | None = None
        if request.regime_stability == "TRANSITIONING":
            transition_warning = (
                f"Regime changed recently — in {regime.value} "
                f"for {request.days_in_regime or 0} day(s)"
            )

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
