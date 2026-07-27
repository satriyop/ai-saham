"""
MarketContextEngine — first-class application service for market regime assessment.

Third pillar alongside RiskEngine and SignalEngine. Self-sufficient: callers call
evaluate() and get a MarketContext. No caller assembles factor data or reads config.

  evaluate(as_of_date, universe)    — fetches all data from injected repositories
  evaluate_with_data(request)       — pipeline path; caller provides pre-loaded data

Layer: Application
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from src.application.config.market_context_config import MarketContextConfig
from src.application.services.mce_observation_identity import MceObservationIdentity
from src.application.use_case.build_market_context_use_case import (
    BuildMarketContextRequest,
    BuildMarketContextUseCase,
)
from src.domain.value_objects.regime_detection_evidence import (
    RegimeDetectionEvidence,
    RegimeStability,
)

if TYPE_CHECKING:
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_context_repository import MarketContextRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.ports.regime_observation_repository import RegimeObservationRepository
    from src.domain.value_objects.market_context import MarketContext

logger = logging.getLogger(__name__)

# Lookback window for fetching historical candles (longest SMA period + buffer)
_CANDLE_LOOKBACK_DAYS = 180
# Broker flow only needs reference_days lookback (default 20); use a small buffer
_BROKER_LOOKBACK_DAYS = 30


class MarketContextEngine:
    """
    Self-sufficient market regime evaluation service.

    Fetches candles from the injected MarketDataRepository (SQLite cache).
    Optionally fetches foreign flow from BrokerDataRepository (aggregated across universe).
    Data must be pre-fetched via `saham fetch market` — this engine reads only.

    universe: list of ticker symbols used for idx_breadth + foreign_flow calculations.
    When universe is empty, both factors are unavailable.
    """

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        config: MarketContextConfig | None = None,
        universe: list[str] | None = None,
        broker_repository: "BrokerDataRepository | None" = None,
        context_repository: "MarketContextRepository | None" = None,
        regime_observation_repository: "RegimeObservationRepository | None" = None,
        banking_universe: list[str] | None = None,
        mce_identity: MceObservationIdentity | None = None,
    ) -> None:
        self._repo = market_repository
        self._broker_repo = broker_repository
        self._context_repo = context_repository
        self._obs_repo = regime_observation_repository
        self._config = config or MarketContextConfig()
        self._universe = [t.upper() for t in (universe or [])]
        self._banking_universe = [t.upper() for t in (banking_universe or [])]
        self._mce_identity = mce_identity
        self._use_case = BuildMarketContextUseCase()

    def evaluate(
        self,
        as_of_date: date | None = None,
    ) -> "MarketContext":
        """
        Full self-contained evaluation.

        Reads all factor data from the local SQLite cache.
        Returns MarketContext with staleness/coverage warnings if data is missing.
        A2: also computes RegimeDetectionEvidence, persists it, and backfills
        forward labels for prior observations.
        """
        as_of = as_of_date or date.today()
        start = as_of - timedelta(days=_CANDLE_LOOKBACK_DAYS)

        cfg = self._config

        vix_candles = self._fetch(cfg.vix.ticker, start, as_of)
        eido_candles = self._fetch(cfg.eido.ticker, start, as_of)
        ihsg_candles = self._fetch(cfg.idx_trend.benchmark_ticker, start, as_of)
        usd_idr_candles = self._fetch(cfg.usd_idr.ticker, start, as_of)

        universe_candles: dict = {}
        if cfg.idx_breadth.enabled and self._universe:
            for ticker in self._universe:
                candles = self._fetch(ticker, start, as_of)
                if candles:
                    universe_candles[ticker] = candles

        foreign_flow_series = (
            self._aggregate_foreign_flow(as_of) if cfg.foreign_flow.enabled else []
        )

        # ── Pass 1: compute regime without stability (current regime unknown yet) ─
        request = BuildMarketContextRequest(
            config=cfg,
            as_of_date=as_of,
            vix_candles=vix_candles,
            eido_candles=eido_candles,
            ihsg_candles=ihsg_candles,
            usd_idr_candles=usd_idr_candles,
            universe_candles=universe_candles,
            foreign_flow_series=foreign_flow_series,
            days_in_regime=None,
            regime_stability=None,
            banking_universe=self._banking_universe,
        )
        result = self._use_case.execute(request)
        current_regime = result.context.regime.value

        # ── A2: stability now computed relative to the actual current regime ──
        # Must happen AFTER the regime is known; prior[0].regime may differ.
        days_in, stability = self._compute_stability(as_of, current_regime)

        # ── Pass 2: rebuild context with correct stability fields ─────────────
        if days_in is not None or stability is not None:
            import dataclasses as _dc

            transition_warning: str | None = None
            if stability == "TRANSITIONING":
                transition_warning = (
                    f"Regime changed recently — in {current_regime} for {days_in or 0} day(s)"
                )
            result_context = _dc.replace(
                result.context,
                regime_stability=stability,
                days_in_regime=days_in,
                transition_warning=transition_warning,
            )
        else:
            result_context = result.context

        context = result_context
        self._persist(context)

        # ── A2: persist regime observation fingerprint ─────────────────────────
        evidence = self._build_evidence(context, result.regime_detection_inputs, as_of)
        self._persist_observation(evidence)  # safe upsert: forward labels preserved by COALESCE

        # ── A2: backfill forward labels for T-5, T-10, T-20 ──────────────────
        self._backfill_forward_labels(as_of, ihsg_candles)

        return context

    def get_snapshot(self, as_of_date: date) -> "MarketContext | None":
        """Return a stored snapshot without re-evaluating. None if none persisted."""
        if self._context_repo is None:
            return None
        return self._context_repo.get(as_of_date)

    def get_recent_snapshots(self, limit: int = 30) -> "list[MarketContext]":
        """Return recent stored snapshots, newest first. Empty if no repo injected."""
        if self._context_repo is None:
            return []
        return self._context_repo.get_recent(limit)

    def _compute_stability(self, as_of: date, current_regime: str) -> tuple[int | None, str | None]:
        """Query prior observations to compute days_in_regime and regime_stability.

        `current_regime` must be the NEWLY computed regime for as_of (not prior[0].regime),
        so that a regime change on as_of produces streak=0/TRANSITIONING, not inheriting the
        prior regime's streak.

        Returns (days_in_regime, regime_stability_str).
        Both are None when no observation repository is configured.
        """
        if self._obs_repo is None:
            return None, None
        cohort_id = self._mce_identity.cohort_id if self._mce_identity else None
        try:
            prior = self._obs_repo.get_recent(limit=60, semantic_compatibility_id=cohort_id)
        except Exception as exc:
            logger.debug("MarketContextEngine: failed to read prior observations: %s", exc)
            return None, None

        if not prior:
            return None, RegimeStability.UNKNOWN.value

        streak = 0
        for obs in prior:
            if obs.observation_date >= as_of:
                continue  # skip same-day or future
            if obs.regime == current_regime:
                streak += 1
            else:
                break

        stable_min_days = 5
        if streak == 0:
            stability = RegimeStability.TRANSITIONING.value
        elif streak >= stable_min_days:
            stability = RegimeStability.STABLE.value
        else:
            stability = RegimeStability.TRANSITIONING.value

        return streak, stability

    def _build_evidence(
        self,
        context: "MarketContext",
        detection_inputs: dict,
        as_of: date,
    ) -> RegimeDetectionEvidence:
        """Assemble a RegimeDetectionEvidence from the computed context and inputs."""
        return RegimeDetectionEvidence(
            observation_date=as_of,
            schema_version=1,
            regime=context.regime.value,
            regime_score=context.conviction,
            regime_confidence=context.regime_confidence or 0.0,
            regime_stability=RegimeStability(context.regime_stability or "UNKNOWN"),
            days_in_regime=context.days_in_regime,
            transition_warning=context.transition_warning,
            ihsg_20d_return=detection_inputs.get("ihsg_20d_return"),
            ihsg_trend_structure=detection_inputs.get("ihsg_trend_structure"),
            ihsg_breadth_pct_above_ma=detection_inputs.get("ihsg_breadth_pct_above_ma"),
            ihsg_volume_trend=detection_inputs.get("ihsg_volume_trend"),
            ihsg_atr_pct=detection_inputs.get("ihsg_atr_pct"),
            idx_foreign_flow_5d=detection_inputs.get("idx_foreign_flow_5d"),
            idx_foreign_flow_20d=detection_inputs.get("idx_foreign_flow_20d"),
            foreign_buy_streak=detection_inputs.get("foreign_buy_streak"),
            foreign_sell_streak=detection_inputs.get("foreign_sell_streak"),
            banking_sector_vs_ihsg=detection_inputs.get("banking_sector_vs_ihsg"),
            sector_breadth=detection_inputs.get("sector_breadth"),
        )

    def _persist_observation(self, evidence: RegimeDetectionEvidence) -> None:
        if self._obs_repo is None:
            return
        if self._mce_identity is not None:
            import dataclasses as _dc

            evidence = _dc.replace(
                evidence,
                semantic_compatibility_id=self._mce_identity.cohort_id,
                observation_contract=self._mce_identity.observation_contract,
                universe_name=self._mce_identity.universe_name,
                benchmark_ticker=self._mce_identity.benchmark_ticker,
            )
        try:
            self._obs_repo.save(evidence)
        except Exception as exc:
            logger.debug("MarketContextEngine: failed to persist regime observation: %s", exc)

    def _backfill_forward_labels(self, as_of: date, ihsg_candles: list) -> None:
        """Retroactively fill forward IHSG return labels for T-5, T-10, T-20 observations.

        Offsets are in TRADING SESSIONS (candle index), not calendar days,
        so weekends and IDX holidays do not mislabel prior observations.
        """
        if self._obs_repo is None or not ihsg_candles:
            return

        cohort_id = self._mce_identity.cohort_id if self._mce_identity else ""

        # Sort candles ascending by date; use the last candle on or before as_of as T
        sorted_candles = sorted(
            (c for c in ihsg_candles if c.close),
            key=lambda c: c.date,
        )
        if not sorted_candles:
            return

        # Find as_of index (last candle on or before as_of)
        as_of_idx = -1
        for i, c in enumerate(sorted_candles):
            if c.date <= as_of:
                as_of_idx = i

        if as_of_idx < 0:
            return
        as_of_close = float(sorted_candles[as_of_idx].close)

        for session_offset in (5, 10, 20):
            prior_idx = as_of_idx - session_offset
            if prior_idx < 0:
                continue
            prior_candle = sorted_candles[prior_idx]
            prior_close = float(prior_candle.close)
            if prior_close <= 0:
                continue

            fwd_return = round((as_of_close - prior_close) / prior_close, 4)
            try:
                if session_offset == 5:
                    self._obs_repo.update_forward_labels(
                        prior_candle.date,
                        forward_ihsg_return_5d=fwd_return,
                        semantic_compatibility_id=cohort_id,
                    )
                elif session_offset == 10:
                    self._obs_repo.update_forward_labels(
                        prior_candle.date,
                        forward_ihsg_return_10d=fwd_return,
                        semantic_compatibility_id=cohort_id,
                    )
                else:
                    self._obs_repo.update_forward_labels(
                        prior_candle.date,
                        forward_ihsg_return_20d=fwd_return,
                        semantic_compatibility_id=cohort_id,
                    )
            except Exception as exc:
                logger.debug(
                    "MarketContextEngine: failed to backfill forward labels for %s: %s",
                    prior_candle.date,
                    exc,
                )

    def _persist(self, context: "MarketContext") -> None:
        if self._context_repo is None:
            return
        try:
            if self._mce_identity is not None:
                self._context_repo.save(
                    context,
                    semantic_compatibility_id=self._mce_identity.cohort_id,
                    observation_contract=self._mce_identity.observation_contract,
                    universe_name=self._mce_identity.universe_name,
                    benchmark_ticker=self._mce_identity.benchmark_ticker,
                )
            else:
                self._context_repo.save(context)
        except Exception as exc:
            logger.debug("MarketContextEngine: failed to persist snapshot: %s", exc)

    def _aggregate_foreign_flow(self, as_of: date) -> list[tuple[date, Decimal]]:
        """
        Aggregate net foreign flow across all universe tickers by date.

        Returns list of (date, total_net_foreign_value) tuples, sorted ascending.
        Empty list if no broker repository or no universe.
        """
        if not self._broker_repo or not self._universe:
            return []

        start = as_of - timedelta(days=_BROKER_LOOKBACK_DAYS)
        daily_totals: dict[date, Decimal] = defaultdict(Decimal)

        for ticker in self._universe:
            try:
                summaries = self._broker_repo.get_broker_summaries(
                    ticker, start_date=start, end_date=as_of
                )
                for s in summaries:
                    daily_totals[s.date] += s.foreign_net_value
            except Exception as exc:
                logger.debug("MarketContextEngine: broker fetch failed for %s: %s", ticker, exc)

        return sorted(daily_totals.items(), key=lambda x: x[0])

    def evaluate_with_data(self, request: BuildMarketContextRequest) -> "MarketContext":
        """Pipeline path: caller provides pre-loaded data (avoids N+1 fetches in loops).

        NOTE: A2 regime observation persistence and forward-label backfill are intentionally
        skipped here. This path is used for screen/backtest loops where throughput matters
        and full evaluate() would cause N×2 use-case calls. If A2 replay data is needed for
        a batch run, call evaluate() once per date after the loop completes.
        """
        return self._use_case.execute(request).context

    # ── internals ─────────────────────────────────────────────────────────────

    def _fetch(self, ticker: str, start: date, end: date) -> list:
        try:
            return self._repo.get_candles(ticker, start_date=start, end_date=end)
        except Exception as exc:
            logger.debug("MarketContextEngine: fetch failed for %s: %s", ticker, exc)
            return []
