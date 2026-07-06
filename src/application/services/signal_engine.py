"""
SignalEngine — first-class application service for composite signal assessment.

Parallel to RiskEngine. Self-sufficient: callers never instantiate SignalContext,
build provider chains, or wire AssessSignalEvidenceUseCase. Two entry points:

  evaluate()              — self-fetches enrichment from injected providers
  evaluate_with_context() — pipeline path; accepts pre-loaded SignalContext
                            to avoid N+1 fetches in screener loops

Phase 4: canonical path is AssessSignalEvidenceUseCase (staged evidence-first
aggregation). SetupEvidence and FlowConfirmationEvidence are optional inputs;
when absent, those groups are MISSING (excluded from denominator) and confidence
is lowered. Flags from SignalContext still apply as score penalties.

Phase 5: MarketContext is passed into AssessSignalEvidenceRequest so regime
conditioning happens INSIDE the use case before renormalization. The module-level
_apply_market_context() post-multiplier is retired.

Layer: Application
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING, Callable

from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceRequest,
    AssessSignalEvidenceUseCase,
)
from src.application.use_case.assess_signal_use_case import (
    AssessSignalRequest,
    AssessSignalResponse,
    SignalEngineConfig,
)
from src.domain.value_objects.signal_assessment import SignalContext
from src.domain.value_objects.forward_estimates import derive_forward_pe

if TYPE_CHECKING:
    from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
    from src.domain.ports.fundamentals_provider import FundamentalsProvider
    from src.domain.ports.insider_activity_provider import InsiderActivityProvider
    from src.domain.ports.seasonality_provider import SeasonalityProvider
    from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
    from src.domain.ports.forward_estimates_provider import ForwardEstimatesProvider
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Self-sufficient signal evaluation service.

    Owns enrichment provider wiring. Callers never see SignalContext,
    AssessSignalEvidenceUseCase, or provider imports — they call evaluate() and
    get an AssessSignalResponse.

    All providers are optional:
      - bandar_provider:            BandarDetectorProvider (broad_score)
      - seasonality_provider:       SeasonalityProvider (win_rate_pct, avg_monthly_return_pct)
      - analyst_provider:           AnalystConsensusProvider (buy_count, upside_pct)
      - forward_estimates_provider: ForwardEstimatesProvider (forward_pe)
      - fundamentals_provider:      accepted but unused (piotroski moved to GateContext/RiskEngine)

    Missing evidence groups lower confidence; flags from SignalContext apply
    score penalties. No neutral-fill for missing evidence groups.
    """

    def __init__(
        self,
        bandar_provider: "BandarDetectorProvider | None" = None,
        fundamentals_provider: "FundamentalsProvider | None" = None,
        insider_activity_provider: "InsiderActivityProvider | None" = None,
        seasonality_provider: "SeasonalityProvider | None" = None,
        analyst_provider: "AnalystConsensusProvider | None" = None,
        forward_estimates_provider: "ForwardEstimatesProvider | None" = None,
        latest_price_provider: Callable[[str], float | None] | None = None,
        weights: "dict[str, float] | None" = None,
        config: SignalEngineConfig | None = None,
    ) -> None:
        self._config = config or SignalEngineConfig()
        self._evidence_use_case = AssessSignalEvidenceUseCase(config=self._config)
        self._bandar = bandar_provider
        self._fundamentals = fundamentals_provider
        self._insider = insider_activity_provider
        self._seasonality = seasonality_provider
        self._analyst = analyst_provider
        self._forward_estimates = forward_estimates_provider
        self._latest_price_provider = latest_price_provider

    def evaluate(
        self,
        ticker: str,
        as_of_date: date | None = None,
        market_context: "MarketContext | None" = None,
        horizon: str | None = None,
    ) -> AssessSignalResponse:
        """
        Full self-contained evaluation.

        Fetches enrichment from injected providers for flag evaluation.
        Evidence groups (SetupEvidence, FlowConfirmationEvidence) are not
        available in the self-fetch path — confidence will be 0, flags still apply.
        """
        ctx = self._build_signal_context(ticker)
        if as_of_date is not None:
            ctx = replace(ctx, snapshot_date=as_of_date)
        return self._evidence_use_case.execute(
            AssessSignalEvidenceRequest(
                ticker=ticker,
                snapshot_date=ctx.snapshot_date,
                signal_context=ctx,
                market_context=market_context,
                horizon=horizon,
            )
        )

    def build_context(
        self, ticker: str, as_of_date: date | None = None
    ) -> SignalContext:
        """Public accessor for the enrichment SignalContext (observability path).

        Used by AuditSignalUseCase / signal-audit CLI to inspect the exact inputs
        that feed the flag evaluation without re-implementing provider wiring.
        """
        ctx = self._build_signal_context(ticker)
        if as_of_date is not None:
            ctx = replace(ctx, snapshot_date=as_of_date)
        return ctx

    def evaluate_with_context(
        self,
        ticker: str,
        signal_context: SignalContext,
        market_context: "MarketContext | None" = None,
        setup_evidence: "SetupEvidence | None" = None,
        flow_confirmation_evidence: "FlowConfirmationEvidence | None" = None,
        setup_family: str | None = None,
        setup_phase: "SetupPhaseSnapshot | None" = None,
        horizon: str | None = None,
        sector_context_evidence: "SectorContextEvidence | None" = None,
    ) -> AssessSignalResponse:
        """
        Pipeline path: caller supplies pre-loaded SignalContext.

        Intended for screener loops (800+ tickers) where enrichment data is
        already fetched per candidate — avoids N+1 provider calls.

        setup_evidence / flow_confirmation_evidence: when provided, group scores
        are computed from evidence objects. When absent, those groups are MISSING.
        """
        return self._evidence_use_case.execute(
            AssessSignalEvidenceRequest(
                ticker=ticker,
                snapshot_date=signal_context.snapshot_date,
                setup_evidence=setup_evidence,
                flow_confirmation_evidence=flow_confirmation_evidence,
                signal_context=signal_context,
                market_context=market_context,
                setup_family=setup_family,
                setup_phase=setup_phase,
                horizon=horizon,
                sector_context_evidence=sector_context_evidence,
            )
        )

    def evaluate_request(
        self,
        request: AssessSignalRequest,
        market_context: "MarketContext | None" = None,
        horizon: str | None = None,
    ) -> AssessSignalResponse:
        """
        Advanced path: caller provides a full AssessSignalRequest.

        Injects signal_context automatically when the caller hasn't supplied one.
        Evidence groups are not available via this path (flags only).
        """
        ctx = request.signal_context or self._build_signal_context(request.ticker)
        return self._evidence_use_case.execute(
            AssessSignalEvidenceRequest(
                ticker=request.ticker,
                snapshot_date=ctx.snapshot_date,
                signal_context=ctx,
                market_context=market_context,
                horizon=horizon,
            )
        )

    def foreign_flow_quality_from_foreign_flow_score(self, foreign_flow_score: float) -> float:
        cfg = self._config.input_mapping.foreign_flow_score
        if cfg.max_score <= 0:
            return 0.0
        score = foreign_flow_score
        if cfg.clamp:
            score = max(0.0, min(score, cfg.max_score))
        return score / cfg.max_score

    def bandar_max_range(self, optional_signal_count: int) -> int:
        cfg = self._config.scoring.bandar
        if optional_signal_count < 0:
            optional_signal_count = 0
        return (cfg.mandatory_signal_count + optional_signal_count) * cfg.signal_score_unit

    # ── internals ────────────────────────────────────────────────────────────

    def _build_signal_context(self, ticker: str) -> SignalContext:
        """Fetch enrichment from injected providers. Each provider fails gracefully."""
        today = date.today()

        bandar_score: int | None = None
        bandar_max_range: int = self._config.scoring.bandar.default_max_range

        win_rate: float | None = None
        avg_return: float | None = None
        seasonality_total_years: int | None = None
        seasonality_back_years: int | None = None

        buy_pct: float | None = None
        upside_pct: float | None = None
        analyst_current_price: float | None = None

        forward_pe: float | None = None
        latest_price: float | None = None

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
                    bandar_max_range = self.bandar_max_range(num_optional)
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
                    from_date=today - timedelta(
                        days=self._config.enrichment.insider_lookback_days
                    ),
                    to_date=today,
                    action_type="ALL",
                )
                insider_ratio = compute_net_buy_ratio(txns)
                if insider_ratio is None:
                    insider_ratio = 0.0
            except Exception as exc:
                logger.debug("SignalEngine: insider unavailable for %s: %s", ticker, exc)

        # ── seasonality ──────────────────────────────────────────────────────
        if self._seasonality is not None:
            try:
                edge = self._seasonality.get_seasonal_edge(ticker, today.year, today.month)
                if edge is not None:
                    win_rate = edge.win_rate_pct
                    avg_return = edge.avg_monthly_return_pct
                    seasonality_total_years = edge.total_years
                    seasonality_back_years = edge.back_years
            except Exception as exc:
                logger.debug("SignalEngine: seasonality unavailable for %s: %s", ticker, exc)

        # ── analyst consensus ─────────────────────────────────────────────────
        if self._analyst is not None:
            try:
                consensus = self._analyst.get_consensus(ticker)
                if consensus is not None and consensus.buy_ratio is not None:
                    buy_pct = consensus.buy_ratio
                    upside_pct = consensus.upside_pct  # percentage, e.g. 15.0 = 15%
                    analyst_current_price = consensus.current_price
            except Exception as exc:
                logger.debug("SignalEngine: analyst unavailable for %s: %s", ticker, exc)

        # ── forward estimates ─────────────────────────────────────────────────
        if self._forward_estimates is not None:
            try:
                fe = self._forward_estimates.get_forward_estimates(ticker)
                if fe is not None:
                    forward_pe = fe.forward_pe  # None for loss-making companies
                    if forward_pe is None:
                        latest_price = self._latest_price(ticker)
                        forward_pe = derive_forward_pe(
                            fe.forward_eps_1y,
                            latest_price or analyst_current_price,
                        )
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
            seasonality_total_years=seasonality_total_years,
            seasonality_back_years=seasonality_back_years,
            analyst_buy_pct=buy_pct,
            analyst_upside_pct=upside_pct,
            forward_pe=forward_pe,
        )

    def _latest_price(self, ticker: str) -> float | None:
        if self._latest_price_provider is None:
            return None
        try:
            price = self._latest_price_provider(ticker)
        except Exception as exc:
            logger.debug("SignalEngine: latest price unavailable for %s: %s", ticker, exc)
            return None
        return price if price and price > 0 else None
