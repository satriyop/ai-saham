"""
SignalEngine — first-class application service for composite signal assessment.

Parallel to RiskEngine. Self-sufficient: callers never instantiate SignalContext,
build provider chains, or wire AssessSignalUseCase. Two entry points:

  evaluate()              — self-fetches enrichment from injected providers
  evaluate_with_context() — pipeline path; accepts pre-loaded SignalContext
                            to avoid N+1 fetches in screener loops

Layer: Application
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

from src.application.use_case.assess_signal_use_case import (
    AssessSignalRequest,
    AssessSignalResponse,
    AssessSignalUseCase,
)
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalContext,
    SignalStrength,
)

if TYPE_CHECKING:
    from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
    from src.domain.ports.fundamentals_provider import FundamentalsProvider
    from src.domain.ports.insider_activity_provider import InsiderActivityProvider
    from src.domain.ports.seasonality_provider import SeasonalityProvider
    from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
    from src.domain.ports.forward_estimates_provider import ForwardEstimatesProvider
    from src.domain.value_objects.market_context import MarketContext

# Mirror thresholds from AssessSignalUseCase — must stay in sync
_STRONG_THRESHOLD = 70
_MODERATE_THRESHOLD = 45

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Self-sufficient signal evaluation service.

    Owns enrichment provider wiring. Callers never see SignalContext,
    AssessSignalUseCase, or provider imports — they call evaluate() and
    get an AssessSignalResponse.

    All providers are optional:
      - bandar_provider:            BandarDetectorProvider (broad_score)
      - seasonality_provider:       SeasonalityProvider (win_rate_pct, avg_monthly_return_pct)
      - analyst_provider:           AnalystConsensusProvider (buy_count, upside_pct)
      - forward_estimates_provider: ForwardEstimatesProvider (forward_pe)
      - fundamentals_provider:      accepted but unused (piotroski moved to GateContext/RiskEngine)

    Missing providers → neutral (50.0) defaults for those factors.
    A coverage_warning is emitted when ≥ 3/6 factors fall back to neutral.
    """

    def __init__(
        self,
        bandar_provider: "BandarDetectorProvider | None" = None,
        fundamentals_provider: "FundamentalsProvider | None" = None,
        insider_activity_provider: "InsiderActivityProvider | None" = None,
        seasonality_provider: "SeasonalityProvider | None" = None,
        analyst_provider: "AnalystConsensusProvider | None" = None,
        forward_estimates_provider: "ForwardEstimatesProvider | None" = None,
        weights: "dict[str, float] | None" = None,
    ) -> None:
        self._use_case = AssessSignalUseCase(weights=weights)
        self._bandar = bandar_provider
        self._fundamentals = fundamentals_provider
        self._insider = insider_activity_provider
        self._seasonality = seasonality_provider
        self._analyst = analyst_provider
        self._forward_estimates = forward_estimates_provider

    def evaluate(
        self,
        ticker: str,
        as_of_date: date | None = None,
        market_context: "MarketContext | None" = None,
    ) -> AssessSignalResponse:
        """
        Full self-contained evaluation.

        Fetches enrichment from injected providers. Providers that are absent
        or that raise exceptions are silently skipped — their factors fall back
        to neutral (50.0).

        market_context: when provided, applies signal_multiplier to the raw score
        and downgrades ENTER→WATCH when gate_tightening is active.
        """
        ctx = self._build_signal_context(ticker)
        if as_of_date is not None:
            ctx = replace(ctx, snapshot_date=as_of_date)
        response = self._use_case.execute(
            AssessSignalRequest(ticker=ticker, signal_context=ctx)
        )
        return _apply_market_context(response, market_context)

    def evaluate_with_context(
        self,
        ticker: str,
        signal_context: SignalContext,
        market_context: "MarketContext | None" = None,
    ) -> AssessSignalResponse:
        """
        Pipeline path: caller supplies pre-loaded SignalContext.

        Intended for screener loops (800+ tickers) where enrichment data is
        already fetched per candidate — avoids N+1 provider calls.
        """
        response = self._use_case.execute(
            AssessSignalRequest(ticker=ticker, signal_context=signal_context)
        )
        return _apply_market_context(response, market_context)

    def evaluate_request(
        self,
        request: AssessSignalRequest,
        market_context: "MarketContext | None" = None,
    ) -> AssessSignalResponse:
        """
        Advanced path: caller provides a full AssessSignalRequest.

        Injects signal_context automatically when the caller hasn't supplied one.
        """
        response = self._use_case.execute(self._inject_signal_context(request))
        return _apply_market_context(response, market_context)

    # ── internals ────────────────────────────────────────────────────────────

    def _inject_signal_context(self, request: AssessSignalRequest) -> AssessSignalRequest:
        if request.signal_context is not None:
            return request
        ctx = self._build_signal_context(request.ticker)
        return replace(request, signal_context=ctx)

    def _build_signal_context(self, ticker: str) -> SignalContext:
        """Fetch enrichment from injected providers. Each provider fails gracefully."""
        today = date.today()

        bandar_score: int | None = None
        bandar_max_range: int = 6  # default: 3 mandatory signals × ±2

        win_rate: float | None = None
        avg_return: float | None = None

        buy_pct: float | None = None
        upside_pct: float | None = None

        forward_pe: float | None = None

        # ── bandar ───────────────────────────────────────────────────────────
        if self._bandar is not None:
            try:
                snap = self._bandar.get_snapshot(ticker)
                if snap is not None:
                    bandar_score = snap.broad_score
                    # dynamic range: (3 mandatory + num optional top3/5/10) × ±2
                    num_optional = sum(
                        1 for x in [snap.top3_accdist, snap.top5_accdist, snap.top10_accdist]
                        if x is not None
                    )
                    bandar_max_range = (3 + num_optional) * 2
            except Exception as exc:
                logger.debug("SignalEngine: bandar unavailable for %s: %s", ticker, exc)

        # ── insider activity ──────────────────────────────────────────────────
        insider_ratio: float | None = None
        if self._insider is not None:
            try:
                from datetime import timedelta
                from src.domain.value_objects.insider_transaction import compute_net_buy_ratio
                txns = self._insider.get_insider_transactions(
                    ticker=ticker,
                    from_date=today - timedelta(days=90),
                    to_date=today,
                    action_type="ALL",
                )
                insider_ratio = compute_net_buy_ratio(txns)
            except Exception as exc:
                logger.debug("SignalEngine: insider unavailable for %s: %s", ticker, exc)

        # ── seasonality ──────────────────────────────────────────────────────
        if self._seasonality is not None:
            try:
                edge = self._seasonality.get_seasonal_edge(ticker, today.year, today.month)
                if edge is not None:
                    win_rate = edge.win_rate_pct
                    avg_return = edge.avg_monthly_return_pct
            except Exception as exc:
                logger.debug("SignalEngine: seasonality unavailable for %s: %s", ticker, exc)

        # ── analyst consensus ─────────────────────────────────────────────────
        if self._analyst is not None:
            try:
                consensus = self._analyst.get_consensus(ticker)
                if consensus is not None and consensus.analyst_count > 0:
                    buy_pct = consensus.buy_count / consensus.analyst_count  # 0.0–1.0
                    upside_pct = consensus.upside_pct  # percentage, e.g. 15.0 = 15%
            except Exception as exc:
                logger.debug("SignalEngine: analyst unavailable for %s: %s", ticker, exc)

        # ── forward estimates ─────────────────────────────────────────────────
        if self._forward_estimates is not None:
            try:
                fe = self._forward_estimates.get_forward_estimates(ticker)
                if fe is not None:
                    forward_pe = fe.forward_pe  # None for loss-making companies
            except Exception as exc:
                logger.debug("SignalEngine: forward estimates unavailable for %s: %s", ticker, exc)

        return SignalContext(
            ticker=ticker,
            snapshot_date=today,
            bandar_broad_score=bandar_score,
            bandar_max_range=bandar_max_range,
            insider_net_buy_ratio=insider_ratio,
            seasonality_win_rate=win_rate,
            seasonality_avg_return_pct=avg_return,
            analyst_buy_pct=buy_pct,
            analyst_upside_pct=upside_pct,
            forward_pe=forward_pe,
        )


# ── Market context post-processing ───────────────────────────────────────────

def _apply_market_context(
    response: AssessSignalResponse,
    market_context: "MarketContext | None",
) -> AssessSignalResponse:
    """
    Apply regime adjustment to a signal assessment.

    score × signal_multiplier → re-classified strength/entry.
    gate_tightening=True → ENTER is capped to WATCH.
    No-op when market_context is None or multiplier=1.0 and no tightening.
    """
    if market_context is None:
        return response

    multiplier = market_context.signal_multiplier
    tighten = market_context.gate_tightening

    if multiplier == 1.0 and not tighten:
        return response

    base = response.assessment.score
    adjusted = max(0, min(100, round(base * multiplier)))
    raw = response.signal_score_raw if response.signal_score_raw is not None else base

    if adjusted >= _STRONG_THRESHOLD:
        new_strength = SignalStrength.STRONG
    elif adjusted >= _MODERATE_THRESHOLD:
        new_strength = SignalStrength.MODERATE
    else:
        new_strength = SignalStrength.WEAK

    if new_strength == SignalStrength.STRONG:
        new_entry = EntryQuality.ENTER
    elif new_strength == SignalStrength.MODERATE:
        new_entry = EntryQuality.WATCH
    else:
        new_entry = EntryQuality.AVOID

    if tighten and new_entry == EntryQuality.ENTER:
        new_entry = EntryQuality.WATCH

    regime = market_context.regime.value
    note = f" [regime:{regime} ×{multiplier:.2f} {base}→{adjusted}"
    if tighten and new_entry != response.assessment.entry_quality:
        note += " ENTER→WATCH"
    note += "]"

    new_assessment = replace(
        response.assessment,
        score=adjusted,
        strength=new_strength,
        entry_quality=new_entry,
        rationale=response.assessment.rationale + (note,),
    )
    return replace(response, assessment=new_assessment, signal_score_raw=raw)
