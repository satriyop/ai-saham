"""Per-candidate diagnostic evidence assembly for accumulation screening."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.volatility_context import build_volatility_context

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResolver,
    )
    from src.application.services.relative_strength_calculator import (
        RelativeStrengthCalculator,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.application.services.volatility_context import VolatilityContext
    from src.application.use_case.evaluate_swing_setup_use_case import (
        SwingSetupCatalogConfig,
    )
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.institutional_accumulation_evidence import (
        InstitutionalAccumulationEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


_UNSET_SETUP_FAMILY = object()


class AccumulationCandidateEvidenceBuilder:
    """Build diagnostic evidence for one accumulation candidate."""

    def __init__(
        self,
        *,
        market_repository: "MarketDataRepository",
        broker_repository: "BrokerDataRepository",
        signal_engine: "SignalEngine | None",
        candidate_observations_repository: "CandidateObservationsRepository | None",
        swing_setup_catalog: "SwingSetupCatalogConfig | None",
        primary_setup_family_resolver: "PrimarySetupFamilyResolver",
        relative_strength_calculator: "RelativeStrengthCalculator",
        indicator_registry: "IndicatorRegistry",
        ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier] | None = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._signal_engine = signal_engine
        self._candidate_observations_repo = candidate_observations_repository
        self._swing_setup_catalog = swing_setup_catalog
        self._setup_family_resolver = primary_setup_family_resolver
        self._relative_strength_calculator = relative_strength_calculator
        self._indicator_registry = indicator_registry
        self._ticker_profile_classifier_factory = ticker_profile_classifier_factory

    def resolve_preliminary_setup_family(
        self, candidate: "accumulation_dto.AccumulationCandidate"
    ) -> str | None:
        """Stage-1 family resolution before strategy evidence exists."""
        return self._setup_family_resolver.resolve(
            candidate=candidate,
            swing_setup_catalog=self._swing_setup_catalog,
        ).primary_setup_family

    def build_candidate_strategy_evidence(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        setup_phase: "SetupPhaseSnapshot | None",
        snapshot_date: date,
        request: accumulation_dto.AccumulationScreenRequest,
    ) -> "StrategyEvidence | None":
        if request.strategy_name is None:
            return None
        try:
            from src.application.services.strategy_evidence_builder import (
                StrategyEvidenceBuilder,
                StrategyEvidenceRequest,
            )

            candles = self._market_repo.get_candles(
                candidate.ticker,
                end_date=snapshot_date,
            )
            setup_family = self.resolve_preliminary_setup_family(candidate)
            return StrategyEvidenceBuilder().build(
                StrategyEvidenceRequest(
                    ticker=candidate.ticker,
                    strategy_name=request.strategy_name,
                    candles=tuple(candles),
                    snapshot_date=snapshot_date,
                    setup_family=setup_family,
                    setup_phase=setup_phase,
                )
            )
        except Exception:
            return None

    def build_candidate_institutional_accumulation_evidence(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        snapshot_date: date,
    ) -> "InstitutionalAccumulationEvidence | None":
        try:
            from src.application.services.institutional_accumulation_evidence_builder import (
                InstitutionalAccumulationEvidenceBuilder,
                InstitutionalAccumulationEvidenceRequest,
            )

            start_date = snapshot_date - timedelta(days=45)
            candles = self._market_repo.get_candles(candidate.ticker, end_date=snapshot_date)
            broker_daily_flows = tuple(
                self._broker_repo.get_broker_daily_flows(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            foreign_flow_points = tuple(
                self._broker_repo.get_foreign_flow_points(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            broker_summaries = tuple(
                self._broker_repo.get_broker_summaries(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            return InstitutionalAccumulationEvidenceBuilder.from_yaml().build(
                InstitutionalAccumulationEvidenceRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    broker_daily_flows=broker_daily_flows,
                    foreign_flow_points=foreign_flow_points,
                    broker_summaries=broker_summaries,
                    bandar_snapshot=candidate.bandar_detector,
                    candles=tuple(candles),
                )
            )
        except Exception:
            return None

    def build_candidate_ticker_profile(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        snapshot_date: date,
    ) -> "TickerProfileSnapshot | None":
        if self._ticker_profile_classifier_factory is None:
            return None
        try:
            from src.application.dto.ticker_profile import TickerProfileRequest

            start_date = snapshot_date - timedelta(days=45)
            candles = self._market_repo.get_candles(candidate.ticker, end_date=snapshot_date)
            broker_daily_flows = tuple(
                self._broker_repo.get_broker_daily_flows(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            broker_summaries = tuple(
                self._broker_repo.get_broker_summaries(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            market_cap_idr: Decimal | None = None
            if (
                candidate.fundamentals is not None
                and candidate.fundamentals.market_cap_idr is not None
            ):
                market_cap_idr = Decimal(str(candidate.fundamentals.market_cap_idr))
            sector = (
                candidate.ticker_notation.sector
                if candidate.ticker_notation is not None
                else None
            )
            sub_sector = (
                candidate.ticker_notation.sub_sector
                if candidate.ticker_notation is not None
                else None
            )
            classifier = self._ticker_profile_classifier_factory()
            return classifier.classify(
                TickerProfileRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    candles=tuple(candles),
                    broker_daily_flows=broker_daily_flows,
                    broker_summaries=broker_summaries,
                    market_cap_idr=market_cap_idr,
                    sector=sector,
                    sub_sector=sub_sector,
                )
            )
        except Exception:
            return None

    def build_candidate_volatility_context(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        snapshot_date: date,
    ) -> "VolatilityContext":
        """Point-in-time ATR(14) volatility context for one candidate.

        Never raises: an unavailable ATR (e.g. insufficient candle history)
        must not block candidate observation generation, so failures resolve
        to the shared helper's UNKNOWN/None behavior instead.
        """
        atr_value = None
        try:
            candles = self._market_repo.get_candles(candidate.ticker, end_date=snapshot_date)
            atr_values = self._indicator_registry.compute("ATR", candles, 14)
            if atr_values:
                atr_value = atr_values[-1][1]
        except Exception:
            atr_value = None
        return build_volatility_context(
            atr_value=atr_value,
            latest_close=candidate.current_price,
        )

    def build_candidate_sector_context(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        snapshot_date: date,
        tp_snapshot: "TickerProfileSnapshot | None",
    ) -> "SectorContextEvidence | None":
        try:
            from src.application.services.sector_context_evidence_builder import (
                SectorContextEvidenceBuilder,
                SectorContextRequest,
            )

            builder = SectorContextEvidenceBuilder.from_yaml()
            sector = (
                candidate.ticker_notation.sector
                if candidate.ticker_notation is not None
                else None
            ) or (tp_snapshot.sector if tp_snapshot is not None else None)
            peer_tickers = builder.peers_for_ticker(candidate.ticker)
            peer_candles: dict[str, list] = {}
            for peer in peer_tickers:
                try:
                    candles = self._market_repo.get_candles(peer, end_date=snapshot_date)
                    if candles:
                        peer_candles[peer] = list(candles)
                except Exception:
                    pass
            ticker_candles = tuple(
                self._market_repo.get_candles(candidate.ticker, end_date=snapshot_date)
            )
            ihsg_20d_return = _simple_return(
                self._market_repo.get_candles("IHSG", end_date=snapshot_date),
                lookback=20,
                min_valid=18,
            )
            return builder.build(
                SectorContextRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    sector=sector,
                    ticker_candles=ticker_candles,
                    peer_candles=peer_candles,
                    ihsg_20d_return=ihsg_20d_return,
                )
            )
        except Exception:
            return None

    def build_candidate_company_quality_context(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        snapshot_date: date,
    ) -> "CompanyQualityContextEvidence | None":
        """Build DIAGNOSTIC company-quality / ticker-alpha conviction evidence.

        Uses enrichment already loaded on the candidate (forward P/E, analyst,
        insider, seasonality) via the shared SignalContext builder — no extra
        provider fetch. Zero scoring authority (DIAGNOSTIC).
        """
        if self._signal_engine is None:
            return None
        try:
            from src.application.services.company_quality_context_evidence_builder import (
                CompanyQualityContextEvidenceBuilder,
                CompanyQualityContextRequest,
            )

            signal_ctx = build_signal_context_from_candidate(
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                candidate=candidate,
                signal_engine=self._signal_engine,
            )
            return CompanyQualityContextEvidenceBuilder.from_yaml().build(
                CompanyQualityContextRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    signal_context=signal_ctx,
                )
            )
        except Exception:
            return None

    def detect_candidate_setup_phase(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        flow_ev: "FlowConfirmationEvidence | None",
        snapshot_date: date,
        setup_family: "str | None" = _UNSET_SETUP_FAMILY,  # type: ignore[assignment]
    ) -> "SetupPhaseSnapshot | None":
        try:
            from src.application.services.candle_provenance import resolve_candle_source
            from src.application.services.setup_evidence_builder import (
                SetupEvidenceBuilder,
            )
            from src.application.services.setup_phase_detector import SetupPhaseDetector
            from src.application.services.setup_phase_history import (
                load_previous_setup_phases,
            )
            from src.domain.value_objects.benchmark_symbol import (
                CANONICAL_BENCHMARK_TICKER,
            )

            if setup_family is _UNSET_SETUP_FAMILY:
                # Stage 1 resolution: no strategy_evidence yet (it is built
                # later, in the persist loop, using this very phase snapshot
                # as input — see build_candidate_strategy_evidence). Relies
                # only on explicit request family (none today for screen
                # accum) and setup families detected from screen evidence.
                setup_family = self.resolve_preliminary_setup_family(candidate)
            # else: caller (stage 2 recompute in _persist_candidate_observations)
            # supplies the final, strategy-evidence-aware family explicitly —
            # used verbatim, including an explicit None for "genuinely unknown".

            candles = self._market_repo.get_candles(
                candidate.ticker,
                end_date=snapshot_date,
            )
            benchmark_candles = self._market_repo.get_candles(
                CANONICAL_BENCHMARK_TICKER,
                end_date=snapshot_date,
            )
            rs_result = self._relative_strength_calculator.calculate(
                ticker_candles=candles,
                benchmark_candles=benchmark_candles,
                as_of_date=snapshot_date,
            )
            # Attached as diagnostic instance attributes (not formal dataclass
            # fields) so _sub_signal_fingerprint() can read them without
            # threading a new return value through this method's signature.
            candidate.rs_vs_ihsg_5d = rs_result.rs_vs_ihsg_5d
            candidate.rs_vs_ihsg_20d = rs_result.rs_vs_ihsg_20d
            previous_phases = load_previous_setup_phases(
                self._candidate_observations_repo,
                ticker=candidate.ticker,
                before_date=snapshot_date,
                setup_family=setup_family,
            )
            candle_source = resolve_candle_source(
                self._market_repo,
                ticker=candidate.ticker,
                as_of_date=candles[-1].date if candles else snapshot_date,
            )
            setup_evidence = SetupEvidenceBuilder().build(
                candidate,
                None,
                rs_vs_ihsg_5d=rs_result.rs_vs_ihsg_5d,
                volume_trend_ratio=None,
                candle_source=candle_source,
                analysis_date=snapshot_date,
            )
            return SetupPhaseDetector().detect(
                candles=candles,
                setup_eval=None,
                setup_evidence=setup_evidence,
                flow_evidence=flow_ev,
                setup_family=setup_family,
                previous_phases=previous_phases,
            )
        except Exception:
            return None


def _simple_return(
    candles: list[Any] | tuple[Any, ...],
    *,
    lookback: int,
    min_valid: int,
) -> float | None:
    sorted_candles = sorted(candles, key=lambda c: c.date)
    window = sorted_candles[-lookback:] if len(sorted_candles) >= lookback else sorted_candles
    valid = [c for c in window if getattr(c, "close", None) and float(c.close) > 0.0]
    if len(valid) < min_valid:
        return None
    reference = float(valid[0].close)
    if reference <= 0.0:
        return None
    return (float(valid[-1].close) - reference) / reference
