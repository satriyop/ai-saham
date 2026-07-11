"""
AccumulationScreenUseCase — multi-stock foreign accumulation screener.

Scans a list of tickers for sustained foreign investor accumulation patterns.
Foreign-flow scoring is delegated to ScoreForeignFlowUseCase;
this use case owns orchestration, filtering, enrichment, and sorting.

Intraday vs Swing usage:
  This screener produces a SWING WATCHLIST (5–20 day horizon).
  For intraday timing, cross-reference with `saham screen pre-open`.

Layer: Application
Depends on: Domain ports only — no infrastructure imports
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.ports.corporate_action_repository import CorporateActionRepository
from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.accumulation_risk_funnel import AccumulationRiskFunnel
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.use_case.score_foreign_flow_use_case import (
    ScoreForeignFlowRequest,
    ScoreForeignFlowUseCase,
)
from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.forward_estimates_provider import ForwardEstimatesProvider
from src.domain.ports.fundamentals_provider import FundamentalsProvider
from src.domain.ports.insider_activity_provider import InsiderActivityProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.seasonality_provider import SeasonalityProvider
from src.domain.ports.shareholding_provider import ShareholdingProvider
from src.domain.ports.ticker_notation_provider import TickerNotationProvider
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResolver,
    )
    from src.application.services.relative_strength_calculator import (
        RelativeStrengthCalculator,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
    from src.application.use_case.evaluate_swing_setup_use_case import (
        SwingSetupCatalogConfig,
    )
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence

# Default setup targets (1:1 R:R, regime-unaware fallback)
_DEFAULT_TAKE_PROFIT = Decimal("5")
_DEFAULT_STOP_LOSS = Decimal("5")
# Regime-specific targets (validated direction: IHSG has documented regime cycles)
# MCE vocabulary (RISK_ON/NEUTRAL/VOLATILE/RISK_OFF).
_REGIME_TARGETS: dict[str, tuple[Decimal, Decimal]] = {
    "RISK_ON": (Decimal("8"), Decimal("4")),  # 2:1 R:R — trending market
    "NEUTRAL": (Decimal("5"), Decimal("5")),  # 1:1 R:R — range-bound
    "VOLATILE": (Decimal("3"), Decimal("3")),  # tight — minimize exposure
    "RISK_OFF": (Decimal("3"), Decimal("3")),  # capital preservation
}


def resolve_setup_targets(
    regime: str | None,
    config: Any | None = None,
) -> tuple[Decimal, Decimal]:
    """Return (take_profit_pct, stop_loss_pct) for the foreign-bounce setup.

    Precedence: YAML config overrides > regime defaults > hardcoded fallback.
    All values are in percentage points (e.g. Decimal("5") = 5%).
    """
    if config:
        targets = getattr(config, "setup_targets", None)
        if targets is None and isinstance(config, dict):
            targets = config.get("setup_targets", config)
        targets = targets or {}
        regime_key = (regime or "default").lower()
        tier = targets.get(regime_key) or targets.get("default", {})
        if tier:
            if isinstance(tier, dict):
                tp = tier.get("take_profit_pct")
                sl = tier.get("stop_loss_pct")
            else:
                tp = getattr(tier, "take_profit_pct", None)
                sl = getattr(tier, "stop_loss_pct", None)
            if tp is not None and sl is not None:
                return Decimal(str(tp)), Decimal(str(sl))

    if regime and regime.upper() in _REGIME_TARGETS:
        return _REGIME_TARGETS[regime.upper()]

    return _DEFAULT_TAKE_PROFIT, _DEFAULT_STOP_LOSS


def _trade_action_rank(candidate: "accumulation_dto.AccumulationCandidate") -> int:
    if candidate.trade_setup is None:
        return 0
    action = candidate.trade_setup.action.value
    return {
        "ENTER": 5,
        "WATCH": 4,
        "AVOID": 2,
        "BLOCKED_EXECUTION": 1,
        "BLOCKED_STRUCTURAL": 0,
    }.get(action, 0)


def _screen_sort_key(
    candidate: "accumulation_dto.AccumulationCandidate",
) -> tuple[float, float, float, float]:
    """Default screener ordering: verdict, signal, foreign-flow score, seasonality."""
    return (
        float(_trade_action_rank(candidate)),
        float(candidate.signal_assessment.assessment.score if candidate.signal_assessment else 0),
        candidate.foreign_flow_score,
        candidate.seasonal_edge.score if candidate.seasonal_edge else 0.0,
    )


class AccumulationScreenUseCase:
    """
    Scan multiple tickers for foreign accumulation patterns.

    Reads from local repositories only — no network calls.
    All data must be fetched beforehand via `saham fetch market`.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        corporate_action_repo: "CorporateActionRepository | None" = None,
        seasonality_provider: "SeasonalityProvider | None" = None,
        insider_activity_provider: "InsiderActivityProvider | None" = None,
        analyst_consensus_provider: "AnalystConsensusProvider | None" = None,
        forward_estimates_provider: "ForwardEstimatesProvider | None" = None,
        shareholding_provider: "ShareholdingProvider | None" = None,
        bandar_detector_provider: "BandarDetectorProvider | None" = None,
        fundamentals_provider: "FundamentalsProvider | None" = None,
        ticker_notation_provider: "TickerNotationProvider | None" = None,
        idx_groups: "dict[str, list[str]] | None" = None,
        risk_use_case: "AssessRiskUseCase | None" = None,
        signal_engine: "SignalEngine | None" = None,
        candidate_observations_repository: "CandidateObservationsRepository | None" = None,
        foreign_flow_score_use_case: ScoreForeignFlowUseCase | None = None,
        derived_feature_policy: accumulation_dto.AccumulationDerivedFeaturePolicy | None = None,
        swing_setup_catalog: "SwingSetupCatalogConfig | None" = None,
        primary_setup_family_resolver: "PrimarySetupFamilyResolver | None" = None,
        relative_strength_calculator: "RelativeStrengthCalculator | None" = None,
        indicator_registry: "IndicatorRegistry | None" = None,
    ) -> None:
        from src.application.services.bootstrap import create_indicator_registry
        from src.application.services.flow_confirmation_evidence_builder import (
            FlowConfirmationEvidenceBuilder,
        )
        from src.application.services.primary_setup_family_resolver import (
            PrimarySetupFamilyResolver as _PrimarySetupFamilyResolver,
        )
        from src.application.services.relative_strength_calculator import (
            RelativeStrengthCalculator as _RelativeStrengthCalculator,
        )
        from src.application.services.signal_engine import SignalEngine as _SignalEngine

        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._corp_action_repo = corporate_action_repo
        self._seasonality_provider = seasonality_provider
        self._insider_provider = insider_activity_provider
        self._analyst_provider = analyst_consensus_provider
        self._forward_estimates_provider = forward_estimates_provider
        self._shareholding_provider = shareholding_provider
        self._bandar_provider = bandar_detector_provider
        self._fundamentals_provider = fundamentals_provider
        self._ticker_notation_provider = ticker_notation_provider
        self._risk_use_case = risk_use_case
        self._signal_engine = signal_engine or _SignalEngine()
        self._candidate_observations_repo = candidate_observations_repository
        self._foreign_flow_score_uc = foreign_flow_score_use_case or ScoreForeignFlowUseCase()
        self._derived_features = (
            derived_feature_policy or accumulation_dto.AccumulationDerivedFeaturePolicy()
        )
        self._swing_setup_catalog = swing_setup_catalog
        self._setup_family_resolver = primary_setup_family_resolver or _PrimarySetupFamilyResolver()
        self._relative_strength_calculator = (
            relative_strength_calculator or _RelativeStrengthCalculator()
        )
        self._indicator_registry = indicator_registry or create_indicator_registry()
        # Derive weights from the same policy ScoreForeignFlowUseCase uses, so
        # the two can never drift apart (see ADR-039).
        self._flow_confirmation_builder = FlowConfirmationEvidenceBuilder(
            foreign_flow_score_policy=self._foreign_flow_score_uc.policy
        )
        self._candidate_evidence_builder = AccumulationCandidateEvidenceBuilder(
            market_repository=self._market_repo,
            broker_repository=self._broker_repo,
            signal_engine=self._signal_engine,
            candidate_observations_repository=self._candidate_observations_repo,
            swing_setup_catalog=self._swing_setup_catalog,
            primary_setup_family_resolver=self._setup_family_resolver,
            relative_strength_calculator=self._relative_strength_calculator,
            indicator_registry=self._indicator_registry,
        )
        self._risk_funnel = (
            AccumulationRiskFunnel(self._risk_use_case) if self._risk_use_case is not None else None
        )
        self._ticker_to_group: dict[str, str] = {}
        if idx_groups:
            for group_name, tickers in idx_groups.items():
                for t in tickers:
                    self._ticker_to_group[t.upper()] = group_name

        from src.application.services.accumulation_candidate_evaluator import (
            AccumulationCandidateEvaluator,
        )
        from src.application.services.accumulation_candidate_observation_persister import (
            AccumulationCandidateObservationPersister,
        )
        from src.application.services.accumulation_sector_breadth import (
            AccumulationSectorBreadthApplier,
        )

        self._candidate_evaluator = AccumulationCandidateEvaluator(
            broker_repository=self._broker_repo,
            market_repository=self._market_repo,
            derived_feature_policy=self._derived_features,
        )
        self._observation_persister = AccumulationCandidateObservationPersister(
            candidate_observations_repository=self._candidate_observations_repo,
            candidate_evidence_builder=self._candidate_evidence_builder,
            setup_family_resolver=self._setup_family_resolver,
            swing_setup_catalog=self._swing_setup_catalog,
        )
        self._sector_breadth_applier = AccumulationSectorBreadthApplier(
            ticker_to_group=self._ticker_to_group
        )

    def execute(
        self, request: accumulation_dto.AccumulationScreenRequest
    ) -> accumulation_dto.AccumulationScreenResponse:
        today = request.as_of_date or date.today()
        candidates: list[accumulation_dto.AccumulationCandidate] = []
        # Collects (candidate, screen_result, flow_ev) for ALL evaluated tickers —
        # survivors and filtered-out alike. Rejected records are negative samples
        # for future tuning (Phase 7: "rejected candidates become learnable").
        all_results: list[
            tuple[accumulation_dto.AccumulationCandidate, str, FlowConfirmationEvidence | None]
        ] = []
        skipped = 0
        uses_stockbit = False

        for ticker in request.tickers:
            result = self._candidate_evaluator.evaluate(
                ticker=ticker,
                window_days=request.window_days,
                today=today,
                min_net_buy_days=request.min_net_buy_days,
                rsi_period=request.rsi_period or self._derived_features.rsi_period,
                sma_period=request.sma_period or self._derived_features.trend_sma_period,
                tier1_broker_codes=request.tier1_broker_codes,
                bci_cluster_min_count=request.bci_cluster_min_count,
                bci_stable_min_count=request.bci_stable_min_count,
            )

            if result is None:
                skipped += 1
                continue

            if result.top_brokers is not None:
                uses_stockbit = True

            # Early pruning: fetch fundamentals first when market_cap or piotroski
            # gates are active. Avoids 6+ enrichment queries for tickers that will
            # be skipped by these structural filters.
            fundamentals_fetched = False
            if self._fundamentals_provider is not None and (
                request.min_market_cap_idr > 0 or request.min_piotroski > 0
            ):
                result.fundamentals = self._fundamentals_provider.get_fundamentals(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )
                fundamentals_fetched = True

                # Market cap floor gate
                if request.min_market_cap_idr > 0 and (
                    result.fundamentals is None
                    or result.fundamentals.market_cap_idr is None
                    or result.fundamentals.market_cap_idr < request.min_market_cap_idr
                ):
                    cap_b = (
                        result.fundamentals.market_cap_idr // 1_000_000_000
                        if result.fundamentals and result.fundamentals.market_cap_idr
                        else None
                    )
                    logger.debug(
                        "Skip %s: market_cap %sB IDR < floor %dB IDR",
                        result.ticker,
                        cap_b,
                        request.min_market_cap_idr // 1_000_000_000,
                    )
                    skipped += 1
                    continue

                # Piotroski floor gate
                if request.min_piotroski > 0:
                    fscore = (
                        result.fundamentals.piotroski_f_score
                        if result.fundamentals is not None
                        else None
                    )
                    if fscore is None or fscore < request.min_piotroski:
                        skipped += 1
                        continue

            evidence_resp = self._foreign_flow_score_uc.execute(
                ScoreForeignFlowRequest(
                    ticker=result.ticker,
                    snapshot_date=today,
                    net_buy_ratio=result.net_buy_ratio,
                    consecutive_streak=result.consecutive_streak,
                    vwap_discount_pct=result.vwap_discount_pct,
                    rsi=result.rsi,
                    avg_flow_ratio=result.avg_flow_ratio,
                    bb_width_pctile=result.bb_width_pctile,
                    bci_label=result.bci_label,
                    bci_tier1_count=result.bci_tier1_count,
                )
            )
            result.foreign_flow_score_breakdown = evidence_resp.evidence
            result.foreign_flow_score = evidence_resp.evidence.foreign_flow_score
            result.foreign_flow_evidence = ForeignFlowEvidence.from_score_breakdown(
                evidence_resp.evidence,
                net_buy_days=result.net_buy_days,
                total_days=result.total_days,
                vwap_pct=result.vwap_pct,
                longer_term_context={
                    "bci_label": result.bci_label,
                    "bci_tier1_count": result.bci_tier1_count,
                },
            )

            # Phase 2.2: resistance-proximity flag
            if (
                request.resistance_gate_enabled
                and result.nearest_resistance_pct is not None
                and result.nearest_resistance_pct < request.resistance_headroom_min_pct
            ):
                result.resistance_flag = True

            # Phase 3.1: corporate action risk flags (dividend, rights issue, RUPS)
            if self._corp_action_repo is not None:
                from datetime import timedelta

                events = self._corp_action_repo.get_upcoming_events(
                    ticker=result.ticker,
                    from_date=today,
                    to_date=today + timedelta(days=request.ex_date_warning_days),
                )
                for event in events:
                    if event.is_dividend:
                        result.dividend_risk = True
                    elif event.is_rights_issue:
                        result.rights_issue_risk = True
                    elif event.is_rups:
                        result.upcoming_rups.append(event.detail or "RUPS")

            # Phase 3.3: seasonality signal
            if self._seasonality_provider is not None:
                result.seasonal_edge = self._seasonality_provider.get_seasonal_edge(
                    ticker=result.ticker,
                    year=today.year,
                    month=today.month,
                    as_of_date=request.as_of_date,
                )

            # Insider activity: director/commissioner transactions in last 90 days
            insider_txns: list = []
            insider_net_buy_ratio: float | None = None
            if self._insider_provider is not None:
                from datetime import timedelta

                from src.domain.value_objects.insider_transaction import compute_net_buy_ratio

                insider_txns = self._insider_provider.get_insider_transactions(
                    ticker=result.ticker,
                    from_date=today - timedelta(days=self._derived_features.insider_lookback_days),
                    to_date=today,
                    action_type="ALL",
                    as_of_date=request.as_of_date,
                )
                buy_txns = [t for t in insider_txns if t.is_buy]
                if buy_txns:
                    result.insider_buying = True
                    result.recent_insider_buys = [t.label for t in buy_txns[:3]]
                insider_net_buy_ratio = compute_net_buy_ratio(insider_txns)
                if insider_net_buy_ratio is None:
                    insider_net_buy_ratio = 0.0

            # Analyst consensus: aggregated buy/hold/sell + price target
            if self._analyst_provider is not None:
                result.analyst_consensus = self._analyst_provider.get_consensus(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            # Shareholding composition: institutional %, individual %, top holder
            if self._shareholding_provider is not None:
                result.shareholding = self._shareholding_provider.get_composition(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            # Bandar detector: Stockbit's institutional operator accumulation signal
            if self._bandar_provider is not None:
                result.bandar_detector = self._bandar_provider.get_snapshot(
                    ticker=result.ticker,
                    session_date=request.as_of_date,
                )

            # Company fundamentals (skip if already fetched by early gate above)
            if self._fundamentals_provider is not None and not fundamentals_fetched:
                result.fundamentals = self._fundamentals_provider.get_fundamentals(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            if self._ticker_notation_provider is not None:
                result.ticker_notation = self._ticker_notation_provider.get_notation(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            # Forward EPS estimates — used in composite score
            if self._forward_estimates_provider is not None:
                result.forward_estimates = self._forward_estimates_provider.get_forward_estimates(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )
                if (
                    result.forward_estimates is not None
                    and result.forward_estimates.forward_pe is None
                    and result.forward_estimates.forward_eps_1y is not None
                    and result.current_price > Decimal("0")
                ):
                    result.forward_estimates = result.forward_estimates.with_current_price(
                        float(result.current_price)
                    )

            result.insider_net_buy_ratio = insider_net_buy_ratio
            signal_ctx = build_signal_context_from_candidate(
                ticker=result.ticker,
                snapshot_date=today,
                candidate=result,
                signal_engine=self._signal_engine,
            )
            # Flow evidence is built from candidate data already in memory — no
            # extra fetch. SetupEvidence is intentionally absent here: the batch
            # screener does not evaluate named setup patterns per ticker; that
            # happens only in the per-ticker swing workflow. Confidence will be
            # 0.40 (flow group only) until the full workflow enriches it further.
            _flow_ev = None
            try:
                _flow_ev = self._flow_confirmation_builder.build(result, analysis_date=today)
            except Exception:
                pass
            result.signal_assessment = self._signal_engine.evaluate_with_context(
                result.ticker, signal_ctx, flow_confirmation_evidence=_flow_ev
            )
            # Accumulation-lifecycle diagnostic for screen display and persisted
            # observations alike — computed once here and reused by
            # _persist_candidate_observations() to avoid detecting twice.
            result.setup_phase = self._candidate_evidence_builder.detect_candidate_setup_phase(
                result, _flow_ev, today
            )

            if (
                request.min_foreign_flow_score_enabled
                and result.foreign_flow_score < request.min_foreign_flow_score
            ):
                all_results.append((result, "rejected_flow", _flow_ev))
                continue
            if request.min_signal_score_enabled and (
                result.signal_assessment is None
                or result.signal_assessment.assessment.score < request.min_signal_score
            ):
                all_results.append((result, "rejected_signal", _flow_ev))
                continue
            all_results.append((result, "pass", _flow_ev))
            candidates.append(result)

        # Phase 3.2: sector breadth post-processing pass
        if request.sector_breadth_enabled and self._ticker_to_group:
            self._sector_breadth_applier.apply(candidates, request)

        # Phase E (Rec 14): post-screening risk funnel — runs only on survivors,
        # not on all 800+ tickers. Reuses already-loaded fundamentals + bandar
        # data from candidates (Rec 15 data sharing — zero extra provider queries).
        if self._risk_funnel is not None:
            self._risk_funnel.run(candidates, today)

        candidates.sort(key=_screen_sort_key, reverse=True)
        self._observation_persister.persist(all_results, today, request)

        return accumulation_dto.AccumulationScreenResponse(
            candidates=candidates,
            screened_at=today,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=skipped,
            provider="stockbit" if uses_stockbit else "idx",
        )

    def _persist_candidate_observations(
        self,
        all_results: list[
            tuple[accumulation_dto.AccumulationCandidate, str, FlowConfirmationEvidence | None]
        ],
        snapshot_date: date,
        request: accumulation_dto.AccumulationScreenRequest,
    ) -> None:
        self._observation_persister.persist(all_results, snapshot_date, request)

    def _evaluate_ticker(
        self,
        ticker: str,
        window_days: int,
        today: date,
        min_net_buy_days: int,
        rsi_period: int,
        sma_period: int,
        tier1_broker_codes: frozenset[str] = accumulation_dto.TIER1_FOREIGN_BROKERS,
        bci_cluster_min_count: int = 3,
        bci_stable_min_count: int = 1,
    ) -> accumulation_dto.AccumulationCandidate | None:
        return self._candidate_evaluator.evaluate(
            ticker=ticker,
            window_days=window_days,
            today=today,
            min_net_buy_days=min_net_buy_days,
            rsi_period=rsi_period,
            sma_period=sma_period,
            tier1_broker_codes=tier1_broker_codes,
            bci_cluster_min_count=bci_cluster_min_count,
            bci_stable_min_count=bci_stable_min_count,
        )

    def _apply_sector_breadth(
        self,
        candidates: list[accumulation_dto.AccumulationCandidate],
        request: accumulation_dto.AccumulationScreenRequest,
    ) -> None:
        self._sector_breadth_applier.apply(candidates, request)
