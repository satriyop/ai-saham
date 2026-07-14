"""Setup evidence / setup phase assembly, shared by evidence coordinators.

Layer: Application

`SwingAnalysisEvidenceBuilder` and `AccumulationCandidateEvidenceBuilder` both
build a `SetupEvidence` snapshot and feed it into `SetupPhaseDetector`, using
the same candle-provenance lookup and persisted-phase history. Swing analysis
already has a `setup_eval` (from `evaluate_swing_setup`) and a resolved
`setup_family`, so it only needs the plain build+detect path. Accumulation
screening runs before a strategy is evaluated, so it also needs relative
strength computed against the benchmark to feed `SetupEvidence.rs_vs_ihsg_5d`.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from src.application.services.candle_provenance import resolve_candle_source
from src.application.services.setup_evidence_builder import SetupEvidenceBuilder
from src.application.services.setup_phase_detector import (
    SetupPhaseConfig,
    SetupPhaseDetector,
)
from src.application.services.setup_phase_history import load_previous_setup_phases
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER

if TYPE_CHECKING:
    from src.application.services.relative_strength_calculator import (
        RelativeStrengthCalculator,
    )
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot


class CandidateSetupPhaseEvidenceAssembler:
    """Builds SetupEvidence and detects SetupPhaseSnapshot from repository data."""

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        candidate_observations_repository: "CandidateObservationsRepository | None",
    ) -> None:
        self._market_repo = market_repository
        self._candidate_observations_repo = candidate_observations_repository

    def build_setup_evidence(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        candles: list[Any] | tuple[Any, ...],
        candidate: Any,
        setup_eval: Any | None,
        rs_vs_ihsg_5d: float | None = None,
        volume_trend_ratio: float | None = None,
    ) -> "SetupEvidence":
        candle_source = resolve_candle_source(
            self._market_repo,
            ticker=ticker,
            as_of_date=candles[-1].date if candles else snapshot_date,
        )
        return SetupEvidenceBuilder().build(
            candidate,
            setup_eval,
            rs_vs_ihsg_5d=rs_vs_ihsg_5d,
            volume_trend_ratio=volume_trend_ratio,
            candle_source=candle_source,
            analysis_date=snapshot_date,
        )

    def detect_setup_phase(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        candles: list[Any] | tuple[Any, ...],
        setup_eval: Any | None,
        setup_evidence: "SetupEvidence | None",
        flow_evidence: "FlowConfirmationEvidence | None",
        setup_family: str | None,
        config: SetupPhaseConfig | None = None,
    ) -> "SetupPhaseSnapshot":
        previous_phases = load_previous_setup_phases(
            self._candidate_observations_repo,
            ticker=ticker,
            before_date=snapshot_date,
            setup_family=setup_family,
        )
        return SetupPhaseDetector().detect(
            candles=candles,
            setup_eval=setup_eval,
            setup_evidence=setup_evidence,
            flow_evidence=flow_evidence,
            setup_family=setup_family,
            previous_phases=previous_phases,
            config=config,
        )

    def detect_setup_phase_with_relative_strength(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        candidate: Any,
        flow_evidence: "FlowConfirmationEvidence | None",
        setup_family: str | None,
        relative_strength_calculator: "RelativeStrengthCalculator",
    ) -> "SetupPhaseSnapshot":
        """Stage-1 accumulation screening path: no `setup_eval` exists yet, so
        relative strength is computed here (instead of reused from a prior
        strategy evaluation) to populate `SetupEvidence.rs_vs_ihsg_5d`.
        """
        candles = self._market_repo.get_candles(ticker, end_date=snapshot_date)
        benchmark_candles = self._market_repo.get_candles(
            CANONICAL_BENCHMARK_TICKER, end_date=snapshot_date
        )
        rs_result = relative_strength_calculator.calculate(
            ticker_candles=candles,
            benchmark_candles=benchmark_candles,
            as_of_date=snapshot_date,
        )
        # Attached as diagnostic instance attributes (not formal dataclass
        # fields) so _sub_signal_fingerprint() can read them without
        # threading a new return value through this method's signature.
        candidate.rs_vs_ihsg_5d = rs_result.rs_vs_ihsg_5d
        candidate.rs_vs_ihsg_20d = rs_result.rs_vs_ihsg_20d
        setup_evidence = self.build_setup_evidence(
            ticker=ticker,
            snapshot_date=snapshot_date,
            candles=candles,
            candidate=candidate,
            setup_eval=None,
            rs_vs_ihsg_5d=rs_result.rs_vs_ihsg_5d,
        )
        return self.detect_setup_phase(
            ticker=ticker,
            snapshot_date=snapshot_date,
            candles=candles,
            setup_eval=None,
            setup_evidence=setup_evidence,
            flow_evidence=flow_evidence,
            setup_family=setup_family,
        )
