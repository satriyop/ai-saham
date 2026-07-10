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
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from src.application.dto import accumulation_screen as accumulation_dto
from src.domain.ports.candidate_observations_repository import CandidateObservation

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResolver,
        PrimarySetupFamilyResult,
    )
    from src.application.services.relative_strength_calculator import (
        RelativeStrengthCalculator,
    )
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse
    from src.application.use_case.evaluate_swing_setup_use_case import (
        SwingSetupCatalogConfig,
    )
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.value_objects.analyst_consensus import AnalystConsensus
    from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
    from src.domain.value_objects.company_fundamentals import CompanyFundamentals
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.forward_estimates import ForwardEstimates
    from src.domain.value_objects.institutional_accumulation_evidence import InstitutionalAccumulationEvidence
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.risk_assessment import RiskAssessment
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot
    from src.domain.value_objects.seasonal_edge import SeasonalEdge
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.shareholding_composition import ShareholdingComposition
    from src.domain.value_objects.ticker_notation import TickerNotationSnapshot
    from src.domain.value_objects.trade_setup import TradeSetup
    from src.application.services.volatility_context import VolatilityContext

from src.application.ports.corporate_action_repository import CorporateActionRepository
from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
)
from src.application.services.accumulation_risk_funnel import AccumulationRiskFunnel
from src.application.services.accumulation_technical_features import (
    compute_accumulation_rsi,
    compute_accumulation_trend,
    compute_bb_squeeze,
    compute_resistance_levels,
)
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.stats import foreign_vwap_discount_pct
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
from src.domain.value_objects.idx_market import SHARES_PER_LOT

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


def _is_usable_broker_summary(summary) -> bool:
    """Return True when a broker summary is safe for accumulation metrics."""
    return (
        summary.total_value > Decimal("0")
        and summary.total_lot >= 0
        and summary.foreign_buy_lot >= 0
        and summary.foreign_sell_lot >= 0
    )


# Broker Concentration Index (BCI) tiers
BCI_CLUSTER = "CLUSTER"  # 3+ Tier 1 codes in window top net-buyers → +15 pts
BCI_STABLE = "STABLE"  # 1–2 Tier 1 codes                         → +5 pts
BCI_RETAIL = "RETAIL-LED"  # 0 Tier 1 codes                           → +0 pts


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


def _screen_sort_key(candidate: "accumulation_dto.AccumulationCandidate") -> tuple[float, float, float, float]:
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
        from src.application.services.signal_engine import SignalEngine as _SignalEngine
        from src.application.services.flow_confirmation_evidence_builder import (
            FlowConfirmationEvidenceBuilder,
        )
        from src.application.services.primary_setup_family_resolver import (
            PrimarySetupFamilyResolver as _PrimarySetupFamilyResolver,
        )
        from src.application.services.relative_strength_calculator import (
            RelativeStrengthCalculator as _RelativeStrengthCalculator,
        )
        from src.application.services.bootstrap import create_indicator_registry

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
        self._derived_features = derived_feature_policy or accumulation_dto.AccumulationDerivedFeaturePolicy()
        self._swing_setup_catalog = swing_setup_catalog
        self._setup_family_resolver = (
            primary_setup_family_resolver or _PrimarySetupFamilyResolver()
        )
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
            AccumulationRiskFunnel(self._risk_use_case)
            if self._risk_use_case is not None
            else None
        )
        # idx_groups: {group_name: [ticker, ...]} from config/idx_groups.yaml
        # Build a reverse map: ticker → group_name for fast lookup
        self._ticker_to_group: dict[str, str] = {}
        if idx_groups:
            for group_name, tickers in idx_groups.items():
                for t in tickers:
                    self._ticker_to_group[t.upper()] = group_name

    def execute(self, request: accumulation_dto.AccumulationScreenRequest) -> accumulation_dto.AccumulationScreenResponse:
        today = request.as_of_date or date.today()
        candidates: list[accumulation_dto.AccumulationCandidate] = []
        # Collects (candidate, screen_result, flow_ev) for ALL evaluated tickers —
        # survivors and filtered-out alike. Rejected records are negative samples
        # for future tuning (Phase 7: "rejected candidates become learnable").
        all_results: list[tuple[accumulation_dto.AccumulationCandidate, str, FlowConfirmationEvidence | None]] = []
        skipped = 0
        uses_stockbit = False

        for ticker in request.tickers:
            result = self._evaluate_ticker(
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
            self._apply_sector_breadth(candidates, request)

        # Phase E (Rec 14): post-screening risk funnel — runs only on survivors,
        # not on all 800+ tickers. Reuses already-loaded fundamentals + bandar
        # data from candidates (Rec 15 data sharing — zero extra provider queries).
        if self._risk_funnel is not None:
            self._risk_funnel.run(candidates, today)

        candidates.sort(key=_screen_sort_key, reverse=True)
        self._persist_candidate_observations(all_results, today, request)

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
        all_results: list[tuple[accumulation_dto.AccumulationCandidate, str, FlowConfirmationEvidence | None]],
        snapshot_date: date,
        request: accumulation_dto.AccumulationScreenRequest,
    ) -> None:
        if self._candidate_observations_repo is None or not all_results:
            return
        try:
            captured_at = datetime.now()
            observations = []
            for c, screen_result, flow_ev in all_results:
                # Reuse the phase already detected in execute() — same candidate,
                # same flow evidence, same snapshot date. Avoids detecting twice.
                setup_phase = c.setup_phase
                strategy_evidence = self._candidate_evidence_builder.build_candidate_strategy_evidence(
                    c,
                    setup_phase,
                    snapshot_date,
                    request,
                )
                ia_evidence = self._candidate_evidence_builder.build_candidate_institutional_accumulation_evidence(
                    c,
                    snapshot_date,
                )
                tp_snapshot = self._candidate_evidence_builder.build_candidate_ticker_profile(c, snapshot_date)
                sc_evidence = self._candidate_evidence_builder.build_candidate_sector_context(
                    c,
                    snapshot_date,
                    tp_snapshot,
                )
                cq_evidence = self._candidate_evidence_builder.build_candidate_company_quality_context(
                    c,
                    snapshot_date,
                )
                volatility_context = self._candidate_evidence_builder.build_candidate_volatility_context(
                    c,
                    snapshot_date,
                )
                # Stage 2 resolution: strategy_evidence, setup_phase, and flow
                # evidence are all available now — final family for this
                # persisted observation.
                preliminary_family = self._candidate_evidence_builder.resolve_preliminary_setup_family(c)
                setup_family_result = self._setup_family_resolver.resolve(
                    candidate=c,
                    strategy_evidence=strategy_evidence,
                    setup_phase=setup_phase,
                    flow_confirmation_evidence=flow_ev,
                    swing_setup_catalog=self._swing_setup_catalog,
                )
                if setup_family_result.primary_setup_family != preliminary_family:
                    # A higher-priority source (e.g. strategy_evidence) revised
                    # the family after phase detection already ran with the
                    # stage-1 preliminary family. Recompute setup_phase with
                    # the final family so the persisted setup_phase and
                    # setup_family always share one contract — attribution
                    # must be able to trust that phase_sequence_valid was
                    # evaluated under the same family as primary_setup_family.
                    setup_phase = self._candidate_evidence_builder.detect_candidate_setup_phase(
                        c,
                        flow_ev,
                        snapshot_date,
                        setup_family=setup_family_result.primary_setup_family,
                    )
                observations.append(
                    CandidateObservation(
                        ticker=c.ticker,
                        snapshot_date=snapshot_date,
                        captured_at=captured_at,
                        payload=build_candidate_observation_payload(
                            c,
                            screen_result=screen_result,
                            flow_ev=flow_ev,
                            setup_phase=setup_phase,
                            strategy_evidence=strategy_evidence,
                            ia_evidence=ia_evidence,
                            tp_snapshot=tp_snapshot,
                            sc_evidence=sc_evidence,
                            cq_evidence=cq_evidence,
                            setup_family_result=setup_family_result,
                            volatility_context=volatility_context,
                            snapshot_date=snapshot_date,
                            captured_at=captured_at,
                            request=request,
                        ),
                    )
                )
            self._candidate_observations_repo.save_many(observations)
        except Exception as exc:
            logger.warning("Candidate observation persistence unavailable: %s", exc)

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
        """Compute accumulation metrics for one ticker."""
        # Load all broker rows up to as_of_date, then select the latest N
        # broker sessions. Calendar-day cutoffs distort IDX windows around
        # weekends, holidays, and data-lag days.
        summaries = self._broker_repo.get_broker_summaries(
            ticker=ticker,
            start_date=None,
            end_date=today,
        )

        if not summaries:
            return None

        summaries = [s for s in summaries if _is_usable_broker_summary(s)]
        if not summaries:
            return None

        window_summaries = sorted(summaries, key=lambda s: s.date)[-window_days:]

        if len(window_summaries) < min_net_buy_days:
            return None

        # Core accumulation metrics
        net_buy_days = sum(1 for s in window_summaries if s.is_foreign_accumulating)
        total_days = len(window_summaries)
        net_buy_ratio = net_buy_days / total_days if total_days > 0 else 0.0
        total_net_value = sum((s.foreign_net_value for s in window_summaries), Decimal("0"))

        # Consecutive buy streak (counting backwards from most recent)
        streak = 0
        for s in sorted(window_summaries, key=lambda x: x.date, reverse=True):
            if s.is_foreign_accumulating:
                streak += 1
            else:
                break

        # Foreign VWAP
        total_buy_value = sum((s.foreign_buy_value for s in window_summaries), Decimal("0"))
        total_buy_lots = sum(s.foreign_buy_lot for s in window_summaries)
        foreign_vwap: Decimal | None = None
        if total_buy_lots > 0:
            try:
                foreign_vwap = (total_buy_value / (total_buy_lots * SHARES_PER_LOT)).quantize(
                    Decimal("0.01")
                )
            except InvalidOperation:
                foreign_vwap = None

        # Avg foreign flow ratio (% of total daily turnover, already in BrokerSummary)
        flow_ratios = [float(s.foreign_flow_ratio) for s in window_summaries if s.total_value > 0]
        avg_flow_ratio = sum(flow_ratios) / len(flow_ratios) if flow_ratios else None

        latest_broker_date = window_summaries[-1].date if window_summaries else None

        # Load candles for price + RSI + trend + BB squeeze
        candles = self._market_repo.get_candles(ticker, end_date=today)
        if not candles:
            current_price = Decimal("0")
            rsi = None
            trend = "SIDE"
            bb_width = None
            bb_width_pctile = None
            latest_candle_date = None
        else:
            current_price = candles[-1].close
            latest_candle_date = candles[-1].date
            rsi = compute_accumulation_rsi(candles, rsi_period)
            trend = compute_accumulation_trend(
                candles,
                sma_period,
                trend_threshold_pct=self._derived_features.trend_threshold_pct,
            )
            bb_width, bb_width_pctile = compute_bb_squeeze(
                candles,
                period=self._derived_features.bb_period,
                history=self._derived_features.bb_history,
            )

        # Phase 2.2: Resistance proximity (MA200 and 52-week high)
        ma200, week52_high, nearest_resistance_pct = compute_resistance_levels(
            candles,
            current_price,
            resistance_ma_period=self._derived_features.resistance_ma_period,
            resistance_high_period=self._derived_features.resistance_high_period,
        )

        # Foreign VWAP discount % — how far foreigners' avg buy is above current price
        vwap_discount_pct = foreign_vwap_discount_pct(foreign_vwap, current_price)

        # Market VWAP % — how far current price is from 20-day all-participant VWAP
        # Negative = price below VWAP (constructive; entering below market average cost basis)
        vwap_pct: float | None = None
        if candles:
            try:
                vwap_window = candles[-self._derived_features.market_vwap_period :]
                total_vol = sum(c.volume for c in vwap_window)
                if total_vol > 0:
                    total_tpv = sum(
                        (c.high + c.low + c.close) / Decimal("3") * c.volume for c in vwap_window
                    )
                    market_vwap = total_tpv / total_vol
                    if market_vwap > 0:
                        vwap_pct = float((current_price - market_vwap) / market_vwap * 100)
            except (InvalidOperation, ZeroDivisionError):
                pass

        # Granular broker info from per-day broker_daily_flow (Stockbit only).
        # These are real daily rows — never period aggregates.
        top_brokers: list[str] | None = None
        institutional_flag = False
        bci_label: str | None = None
        bci_tier1_count: int = 0

        daily_flows = self._broker_repo.get_broker_daily_flows(
            ticker=ticker,
            end_date=today,
        )
        if daily_flows:
            # Collect the window dates from broker summaries to align the window
            window_dates = {s.date for s in window_summaries}
            window_flows = [f for f in daily_flows if f.date in window_dates]

            if window_flows:
                # Aggregate net_lot per broker across the window
                from collections import defaultdict

                broker_net: dict[str, int] = defaultdict(int)
                for f in window_flows:
                    broker_net[f.broker_code] += f.net_lot

                net_buyers = sorted(
                    [(code, net) for code, net in broker_net.items() if net > 0],
                    key=lambda x: x[1],
                    reverse=True,
                )
                if net_buyers:
                    top_brokers = [code for code, _ in net_buyers[:5]]
                    # BCI: count all Tier 1 codes among any net-buyers (not just top 5)
                    all_net_buyer_codes = {code for code, _ in net_buyers}
                    bci_tier1_count = len(all_net_buyer_codes & tier1_broker_codes)
                    if bci_tier1_count >= bci_cluster_min_count:
                        bci_label = BCI_CLUSTER
                    elif bci_tier1_count >= bci_stable_min_count:
                        bci_label = BCI_STABLE
                    else:
                        bci_label = BCI_RETAIL
                    institutional_flag = bci_tier1_count > 0

        return accumulation_dto.AccumulationCandidate(
            ticker=ticker,
            window_days=window_days,
            net_buy_days=net_buy_days,
            total_days=total_days,
            net_buy_ratio=net_buy_ratio,
            total_net_value=total_net_value,
            consecutive_streak=streak,
            foreign_vwap=foreign_vwap,
            current_price=current_price,
            vwap_discount_pct=vwap_discount_pct,
            rsi=rsi,
            trend=trend,
            foreign_flow_score=0.0,  # populated later by ScoreForeignFlowUseCase
            top_brokers=top_brokers,
            institutional_flag=institutional_flag,
            bci_label=bci_label,
            bci_tier1_count=bci_tier1_count,
            vwap_pct=vwap_pct,
            avg_flow_ratio=avg_flow_ratio,
            bb_width=bb_width,
            bb_width_pctile=bb_width_pctile,
            ma200=ma200,
            week52_high=week52_high,
            nearest_resistance_pct=nearest_resistance_pct,
            latest_candle_date=latest_candle_date,
            latest_broker_date=latest_broker_date,
        )

    def _apply_sector_breadth(
        self,
        candidates: list[accumulation_dto.AccumulationCandidate],
        request: accumulation_dto.AccumulationScreenRequest,
    ) -> None:
        """Post-processing: compute sector breadth and apply bonus in-place.

        Groups candidates by idx_groups mapping. For groups with enough members
        (>= min_tickers_for_breadth), computes the fraction with net_buy_ratio > 0.
        Applies sector_breadth_bonus_pts to ALL members of qualifying groups.
        """
        from collections import defaultdict

        # Group candidates by their idx_groups group
        group_candidates: dict[str, list[accumulation_dto.AccumulationCandidate]] = defaultdict(list)
        for candidate in candidates:
            group = self._ticker_to_group.get(candidate.ticker.upper())
            if group:
                group_candidates[group].append(candidate)

        # For each group with enough members, compute breadth and apply bonus
        for group, members in group_candidates.items():
            if len(members) < request.sector_breadth_min_tickers:
                # Set breadth_pct but no bonus (insufficient sample)
                total = len(members)
                positive = sum(1 for m in members if m.net_buy_ratio > 0)
                breadth_pct = positive / total if total > 0 else 0.0
                for m in members:
                    m.sector_breadth_pct = breadth_pct
                continue

            positive = sum(1 for m in members if m.net_buy_ratio > 0)
            breadth_pct = positive / len(members)

            for m in members:
                m.sector_breadth_pct = breadth_pct
                if breadth_pct >= request.sector_breadth_threshold:
                    m.foreign_flow_score += request.sector_breadth_bonus_pts
                    m.sector_breadth_bonus = request.sector_breadth_bonus_pts

def compute_percent_plan(
    entry: "Decimal",
    stop_pct: "Decimal",
    target_pct: "Decimal",
) -> "tuple[Decimal, Decimal]":
    """Compute stop and target prices from a percentage plan."""
    stop = entry * (Decimal("1") - stop_pct / Decimal("100"))
    target = entry * (Decimal("1") + target_pct / Decimal("100"))
    return stop, target


def classify_multi_window_pattern(
    windows: list[int],
    candidates_by_window: dict[int, "accumulation_dto.AccumulationCandidate | None"],
    coiled_spring_min_score: float,
    coiled_spring_bb_pctile: float,
) -> str:
    """
    Label the multi-window accumulation pattern for a single ticker.

    Returns one of: "coiled spring", "sustained", "building",
    "fresh rotation", "long-term only", "mixed", "weak"
    """
    hot = [
        w
        for w in windows
        if candidates_by_window.get(w)
        and candidates_by_window[w].foreign_flow_score >= coiled_spring_min_score
    ]

    for w in windows:
        c = candidates_by_window.get(w)
        if (
            c
            and c.foreign_flow_score >= coiled_spring_min_score
            and c.bb_width_pctile is not None
            and c.bb_width_pctile <= coiled_spring_bb_pctile
        ):
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"
