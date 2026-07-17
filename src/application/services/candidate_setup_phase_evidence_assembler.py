"""Setup evidence / setup phase assembly, shared by evidence coordinators.

Layer: Application

`SwingAnalysisEvidenceBuilder` and `AccumulationCandidateEvidenceBuilder` both
build a `SetupEvidence` snapshot and feed it into `SetupPhaseDetector`, using
the same candle-provenance lookup and persisted-phase history. Swing analysis
already has a `setup_eval` (from `evaluate_swing_setup`) and a resolved
`setup_family`, so it only needs the plain build+detect path. Accumulation
screening runs before a strategy is evaluated, so it also needs benchmark
excess return computed to feed `SetupEvidence.benchmark_excess_return_5_session`
/ `benchmark_excess_return_20_session`.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from src.application.dto.built_evidence import BuiltSetupEvidence
from src.application.services.candle_provenance import resolve_candle_source
from src.application.services.setup_evidence_builder import SetupEvidenceBuilder
from src.application.services.setup_phase_detector import (
    SetupPhaseConfig,
    SetupPhaseDetector,
)
from src.application.services.setup_phase_history import load_previous_setup_phases
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER
from src.domain.value_objects.canonical_signal_evidence_input import (
    CandleRowIdentity,
    SetupProvenance,
)

if TYPE_CHECKING:
    from src.application.services.benchmark_excess_return_calculator import (
        BenchmarkExcessReturnCalculator,
    )
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot


def _normalize_candles(
    candles: "list[Any] | tuple[Any, ...]", *, ticker: str, snapshot_date: date
) -> tuple:
    """Bound a candle sequence to exactly the rows a scored evidence group may
    consume: the correct ticker, no row after `snapshot_date`, deterministic
    ascending date order. The SAME normalized tuple this returns must be used
    for both calculation and provenance — never a wider list for one and a
    narrower one for the other (ADR-041 CANONICAL-EVIDENCE-BOUNDARY)."""
    filtered = [c for c in candles if c.ticker == ticker and c.date <= snapshot_date]
    return tuple(sorted(filtered, key=lambda c: c.date))


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
        benchmark_excess_return_5_session: Any | None = None,
        benchmark_excess_return_20_session: Any | None = None,
        volume_trend_ratio: float | None = None,
        benchmark_candles: "list[Any] | tuple[Any, ...]" = (),
    ) -> BuiltSetupEvidence:
        # Bound once, reused for both calculation and provenance below — a
        # divergent list for one vs. the other is exactly what ADR-041
        # forbids.
        candles = _normalize_candles(candles, ticker=ticker, snapshot_date=snapshot_date)
        benchmark_candles = _normalize_candles(
            benchmark_candles, ticker=CANONICAL_BENCHMARK_TICKER, snapshot_date=snapshot_date
        )
        candle_source = resolve_candle_source(
            self._market_repo,
            ticker=ticker,
            as_of_date=candles[-1].date if candles else snapshot_date,
        )
        evidence = SetupEvidenceBuilder().build(
            candidate,
            setup_eval,
            benchmark_excess_return_5_session=benchmark_excess_return_5_session,
            benchmark_excess_return_20_session=benchmark_excess_return_20_session,
            volume_trend_ratio=volume_trend_ratio,
            candle_source=candle_source,
            analysis_date=snapshot_date,
        )
        benchmark_candle_source = (
            resolve_candle_source(
                self._market_repo,
                ticker=CANONICAL_BENCHMARK_TICKER,
                as_of_date=benchmark_candles[-1].date if benchmark_candles else snapshot_date,
            )
            if benchmark_candles
            else None
        )
        provenance = SetupProvenance(
            ticker=ticker,
            candle_rows=tuple(
                CandleRowIdentity(ticker=c.ticker, date=c.date, source=candle_source)
                for c in candles
            ),
            benchmark_candle_rows=tuple(
                CandleRowIdentity(ticker=c.ticker, date=c.date, source=benchmark_candle_source)
                for c in benchmark_candles
            ),
        )
        return BuiltSetupEvidence(evidence=evidence, provenance=provenance)

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

    def detect_setup_phase_with_benchmark_excess_return(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        candidate: Any,
        flow_evidence: "FlowConfirmationEvidence | None",
        setup_family: str | None,
        benchmark_excess_return_calculator: "BenchmarkExcessReturnCalculator",
    ) -> "SetupPhaseSnapshot":
        """Stage-1 accumulation screening path: no `setup_eval` exists yet, so
        benchmark excess return is computed here (instead of reused from a
        prior strategy evaluation) to populate
        `SetupEvidence.benchmark_excess_return_5_session` /
        `benchmark_excess_return_20_session`.
        """
        raw_ticker_candles = self._market_repo.get_candles(
            ticker,
            end_date=snapshot_date,
        )
        raw_benchmark_candles = self._market_repo.get_candles(
            CANONICAL_BENCHMARK_TICKER,
            end_date=snapshot_date,
        )
        normalized_ticker_candles = _normalize_candles(
            raw_ticker_candles,
            ticker=ticker,
            snapshot_date=snapshot_date,
        )
        normalized_benchmark_candles = _normalize_candles(
            raw_benchmark_candles,
            ticker=CANONICAL_BENCHMARK_TICKER,
            snapshot_date=snapshot_date,
        )
        excess_return_result = benchmark_excess_return_calculator.calculate(
            ticker_candles=normalized_ticker_candles,
            benchmark_candles=normalized_benchmark_candles,
            as_of_date=snapshot_date,
        )
        # Attached as diagnostic instance attributes (not formal dataclass
        # fields) so _sub_signal_fingerprint() can read them without
        # threading a new return value through this method's signature.
        candidate.benchmark_excess_return_5_session = (
            excess_return_result.excess_return_vs_ihsg_5_session
        )
        candidate.benchmark_excess_return_20_session = (
            excess_return_result.excess_return_vs_ihsg_20_session
        )
        built_setup_evidence = self.build_setup_evidence(
            ticker=ticker,
            snapshot_date=snapshot_date,
            candles=normalized_ticker_candles,
            candidate=candidate,
            setup_eval=None,
            benchmark_excess_return_5_session=(
                excess_return_result.excess_return_vs_ihsg_5_session
            ),
            benchmark_excess_return_20_session=(
                excess_return_result.excess_return_vs_ihsg_20_session
            ),
            benchmark_candles=normalized_benchmark_candles,
        )
        return self.detect_setup_phase(
            ticker=ticker,
            snapshot_date=snapshot_date,
            candles=normalized_ticker_candles,
            setup_eval=None,
            setup_evidence=built_setup_evidence.evidence,
            flow_evidence=flow_evidence,
            setup_family=setup_family,
        )
