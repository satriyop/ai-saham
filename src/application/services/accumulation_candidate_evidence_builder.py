"""Per-candidate diagnostic evidence assembly for accumulation screening.

Layer: Application

Repository data loading and per-family evidence assembly live in dedicated
collaborators (`CandidateEvidenceDataLoader` and the
`candidate_*_evidence_assembler` modules) shared with
`SwingAnalysisEvidenceBuilder`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.ports.rules_loader import RulesLoader
from src.application.services.candidate_company_quality_context_evidence_assembler import (
    CandidateCompanyQualityContextEvidenceAssembler,
)
from src.application.services.candidate_evidence_data_loader import (
    CandidateEvidenceDataLoader,
)
from src.application.services.candidate_institutional_accumulation_evidence_assembler import (
    CandidateInstitutionalAccumulationEvidenceAssembler,
)
from src.application.services.candidate_sector_context_evidence_assembler import (
    CandidateSectorContextEvidenceAssembler,
)
from src.application.services.candidate_setup_phase_evidence_assembler import (
    CandidateSetupPhaseEvidenceAssembler,
)
from src.application.services.candidate_ticker_profile_evidence_assembler import (
    CandidateTickerProfileEvidenceAssembler,
)
from src.application.services.volatility_context import build_volatility_context

if TYPE_CHECKING:
    from src.application.services.benchmark_excess_return_calculator import (
        BenchmarkExcessReturnCalculator,
    )
    from src.application.services.company_quality_context_evidence_builder import (
        CompanyQualityContextEvidenceBuilder,
    )
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.application.services.institutional_accumulation_evidence_builder import (
        InstitutionalAccumulationEvidenceBuilder,
    )
    from src.application.services.institutional_flow_config import (
        InstitutionalAccumulationConfig,
    )
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResolver,
        PrimarySetupFamilyResult,
    )
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
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
    from src.domain.ports.learning_artifact_repositories import (
        LearningObservationRepository,
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
    from src.domain.value_objects.setup_evaluation import SetupEvaluation
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


_UNSET_SETUP_FAMILY = object()
_DEFAULT_BENCHMARK = "IHSG"


class AccumulationCandidateEvidenceBuilder:
    """Build diagnostic evidence for one accumulation candidate."""

    def __init__(
        self,
        *,
        market_repository: "MarketDataRepository",
        broker_repository: "BrokerDataRepository",
        signal_engine: "SignalEngine | None",
        candidate_observations_repository: "LearningObservationRepository | None",
        swing_setup_catalog: "SwingSetupCatalogConfig | None",
        primary_setup_family_resolver: "PrimarySetupFamilyResolver",
        benchmark_excess_return_calculator: "BenchmarkExcessReturnCalculator",
        indicator_registry: "IndicatorRegistry",
        rules_loader: RulesLoader,
        ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier] | None = None,
        institutional_accumulation_config_factory: (
            Callable[[], InstitutionalAccumulationConfig] | None
        ) = None,
        sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder] | None = None,
        company_quality_context_builder_factory: (
            Callable[[], CompanyQualityContextEvidenceBuilder] | None
        ) = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._signal_engine = signal_engine
        self._candidate_observations_repo = candidate_observations_repository
        self._swing_setup_catalog = swing_setup_catalog
        self._setup_family_resolver = primary_setup_family_resolver
        self._benchmark_excess_return_calculator = benchmark_excess_return_calculator
        self._indicator_registry = indicator_registry
        self._rules_loader = rules_loader
        self._ticker_profile_classifier_factory = ticker_profile_classifier_factory
        self._sector_context_builder_factory = _normalize_sector_context_factory(
            sector_context_builder_factory
        )

        self._data_loader = CandidateEvidenceDataLoader(market_repository, broker_repository)
        self._setup_phase_assembler = CandidateSetupPhaseEvidenceAssembler(
            market_repository, candidate_observations_repository
        )
        self._institutional_assembler = CandidateInstitutionalAccumulationEvidenceAssembler(
            _normalize_institutional_accumulation_factory(institutional_accumulation_config_factory)
        )
        self._ticker_profile_assembler = CandidateTickerProfileEvidenceAssembler(
            ticker_profile_classifier_factory
        )
        self._sector_context_assembler = CandidateSectorContextEvidenceAssembler()
        self._company_quality_assembler = CandidateCompanyQualityContextEvidenceAssembler(
            _normalize_company_quality_context_factory(company_quality_context_builder_factory)
        )

    def evaluate_named_setups_for_screen(
        self, candidate: "accumulation_dto.AccumulationCandidate"
    ) -> "dict[str, SetupEvaluation]":
        """Evaluate every AVAILABLE_SWING_SETUPS once for discovery capture.

        Screen path intentionally passes broker_detail=None — smart-money
        gates that need broker detail remain honest NO_MATCH. Results are
        diagnostic/research only and do not grant entry authority.
        """
        from src.application.use_case.evaluate_swing_setup_use_case import (
            AVAILABLE_SWING_SETUPS,
            EvaluateSwingSetupRequest,
            EvaluateSwingSetupUseCase,
        )

        if self._swing_setup_catalog is None:
            return {}
        evaluator = EvaluateSwingSetupUseCase()
        evaluations: dict[str, SetupEvaluation] = {}
        for setup_name in AVAILABLE_SWING_SETUPS:
            try:
                evaluations[setup_name] = evaluator.execute(
                    EvaluateSwingSetupRequest(
                        setup_name=setup_name,
                        candidate=candidate,
                        config=self._swing_setup_catalog,
                        broker_detail=None,
                    )
                )
            except Exception:
                continue
        return evaluations

    def resolve_preliminary_setup_family_result(
        self, candidate: "accumulation_dto.AccumulationCandidate"
    ) -> "PrimarySetupFamilyResult":
        """Stage-1 family resolution before strategy evidence exists.

        HIGH-2: this is the single resolution call for the screen path — its
        result is stored on the candidate and reused verbatim by SignalEngine,
        phase detection, and persistence. Never re-resolved after scoring.

        Schema v8: named setup evaluations are computed once here, stored on
        the candidate for fingerprint persistence, and passed into the
        resolver so MATCH-only family detection does not re-evaluate gates.
        """
        named = self.evaluate_named_setups_for_screen(candidate)
        candidate.named_setup_evaluations = named
        return self._setup_family_resolver.resolve(
            candidate=candidate,
            swing_setup_catalog=self._swing_setup_catalog,
            named_setup_evaluations=named,
        )

    def resolve_preliminary_setup_family(
        self, candidate: "accumulation_dto.AccumulationCandidate"
    ) -> str | None:
        """Convenience wrapper returning only the primary family string."""
        return self.resolve_preliminary_setup_family_result(candidate).primary_setup_family

    def build_candidate_strategy_evidence(
        self,
        candidate: "accumulation_dto.AccumulationCandidate",
        setup_phase: "SetupPhaseSnapshot | None",
        snapshot_date: date,
        request: accumulation_dto.AccumulationScreenRequest,
        setup_family: "str | None" = _UNSET_SETUP_FAMILY,  # type: ignore[assignment]
    ) -> "StrategyEvidence | None":
        if request.strategy_name is None:
            return None
        try:
            from src.application.services.strategy_evidence_builder import (
                StrategyEvidenceBuilder,
                StrategyEvidenceRequest,
            )
            from src.application.services.strategy_loader import StrategyLoader

            candles = self._market_repo.get_candles(
                candidate.ticker,
                end_date=snapshot_date,
            )
            if setup_family is _UNSET_SETUP_FAMILY:
                # No caller-supplied family (e.g. tests calling this in
                # isolation) — fall back to resolving it here.
                setup_family = self.resolve_preliminary_setup_family(candidate)
            return StrategyEvidenceBuilder(
                loader=StrategyLoader(rules_loader=self._rules_loader),
            ).build(
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
            inputs = self._data_loader.load_institutional_inputs(
                ticker=candidate.ticker, snapshot_date=snapshot_date
            )
            return self._institutional_assembler.assemble(
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                inputs=inputs,
                bandar_snapshot=candidate.bandar_detector,
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
            inputs = self._data_loader.load_ticker_profile_inputs(
                ticker=candidate.ticker, snapshot_date=snapshot_date
            )
            market_cap_idr: Decimal | None = None
            if (
                candidate.fundamentals is not None
                and candidate.fundamentals.market_cap_idr is not None
            ):
                market_cap_idr = Decimal(str(candidate.fundamentals.market_cap_idr))
            sector = (
                candidate.ticker_notation.sector if candidate.ticker_notation is not None else None
            )
            sub_sector = (
                candidate.ticker_notation.sub_sector
                if candidate.ticker_notation is not None
                else None
            )
            return self._ticker_profile_assembler.assemble(
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                inputs=inputs,
                market_cap_idr=market_cap_idr,
                sector=sector,
                sub_sector=sub_sector,
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
            sc_builder = self._sector_context_builder_factory()
            sector = (
                candidate.ticker_notation.sector if candidate.ticker_notation is not None else None
            ) or (tp_snapshot.sector if tp_snapshot is not None else None)
            peer_tickers = sc_builder.peers_for_ticker(candidate.ticker)
            inputs = self._data_loader.load_sector_context_inputs(
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                sector=sector,
                peer_tickers=peer_tickers,
                benchmark=_DEFAULT_BENCHMARK,
            )
            return self._sector_context_assembler.assemble(
                builder=sc_builder,
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                sector=sector,
                inputs=inputs,
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
            return self._company_quality_assembler.assemble(
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                candidate=candidate,
                signal_engine=self._signal_engine,
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

            return self._setup_phase_assembler.detect_setup_phase_with_benchmark_excess_return(
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                candidate=candidate,
                flow_evidence=flow_ev,
                setup_family=setup_family,
                benchmark_excess_return_calculator=self._benchmark_excess_return_calculator,
            )
        except Exception:
            return None


def _normalize_sector_context_factory(
    builder_factory: "Callable[[], SectorContextEvidenceBuilder] | None",
) -> "Callable[[], SectorContextEvidenceBuilder]":
    if builder_factory is not None:
        return builder_factory

    def _build() -> "SectorContextEvidenceBuilder":
        from src.application.services.sector_context_evidence_builder import (
            SectorContextConfig,
            SectorContextEvidenceBuilder,
        )

        return SectorContextEvidenceBuilder(SectorContextConfig.from_mapping({}), {})

    return _build


def _normalize_institutional_accumulation_factory(
    config_factory: Callable[[], "InstitutionalAccumulationConfig"] | None,
) -> Callable[[], "InstitutionalAccumulationEvidenceBuilder"]:
    def _build() -> "InstitutionalAccumulationEvidenceBuilder":
        from src.application.services.institutional_accumulation_evidence_builder import (
            InstitutionalAccumulationEvidenceBuilder,
        )

        if config_factory is not None:
            return InstitutionalAccumulationEvidenceBuilder(config_factory())
        return InstitutionalAccumulationEvidenceBuilder()

    return _build


def _normalize_company_quality_context_factory(
    builder_factory: Callable[[], "CompanyQualityContextEvidenceBuilder"] | None,
) -> Callable[[], "CompanyQualityContextEvidenceBuilder"]:
    if builder_factory is not None:
        return builder_factory

    def _build() -> "CompanyQualityContextEvidenceBuilder":
        from src.application.services.company_quality_context_evidence_builder import (
            CompanyQualityContextConfig,
            CompanyQualityContextEvidenceBuilder,
        )

        return CompanyQualityContextEvidenceBuilder(CompanyQualityContextConfig.from_mapping({}))

    return _build
