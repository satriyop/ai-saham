from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationCandidateEvaluationResult,
    AccumulationScreenObservationCandidate,
    AccumulationScreenResponse,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
)
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsRequest,
    BackfillSignalObservationsUseCase,
)
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)

_LEAN_IDENTITY = LeanObservationIdentity(
    observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
    semantic_compatibility_id=SemanticCompatibilityId("sha256:" + "c" * 64),
)
from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateAllSignalForwardLabelsResponse,
    GenerateSignalForwardLabelsUseCase,
)
from src.application.use_case.record_accumulation_observations_use_case import (
    RecordAccumulationObservationsResult,
)
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon


class FakeMarketRepository:
    def __init__(self, candles: list[Candle]):
        self.candles = candles
        self.calls = []

    def get_candles(self, ticker, start_date=None, end_date=None):
        self.calls.append((ticker, start_date, end_date))
        ticker = ticker.upper()
        return [
            candle
            for candle in self.candles
            if candle.ticker == ticker
            and (start_date is None or candle.date >= start_date)
            and (end_date is None or candle.date <= end_date)
        ]

    def save_candles(self, candles):
        raise AssertionError("not used")

    def has_data(self, ticker, start_date, end_date):
        raise AssertionError("not used")

    def get_date_range(self, ticker):
        raise AssertionError("not used")


class FakeCandidateObservationsRepository:
    def __init__(self):
        self.by_date: dict[date, list[CandidateObservation]] = {}

    def append(self, ticker: str, snapshot_date: date, window_sessions: int = 7) -> None:
        observations = self.by_date.setdefault(snapshot_date, [])
        observations.append(
            CandidateObservation(
                ticker=ticker.upper(),
                snapshot_date=snapshot_date,
                captured_at=datetime(2026, 7, 7, 12, 0, len(observations)),
                payload={
                    "ticker": ticker.upper(),
                    "snapshot_date": snapshot_date.isoformat(),
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                },
                window_sessions=window_sessions,
                data_as_of_date=snapshot_date,
                config_hash="test-hash",
                latest_completed_session=snapshot_date,
                analysis_as_of=snapshot_date,
                observation_contract=_LEAN_IDENTITY.observation_contract,
                semantic_compatibility_id=_LEAN_IDENTITY.semantic_compatibility_id,
            )
        )

    def save_many(self, observations):
        for observation in observations:
            self.by_date.setdefault(observation.snapshot_date, []).append(observation)

    def get_latest(self, ticker, snapshot_date):
        observations = [
            observation
            for observation in self.by_date.get(snapshot_date, [])
            if observation.ticker == ticker.upper()
        ]
        return observations[-1] if observations else None

    def get_at(self, ticker, snapshot_date, captured_at):
        return None

    def list_recent(self, ticker, *, before_date=None, limit=20):
        return []

    def list_by_date(self, snapshot_date):
        latest_by_ticker = {}
        for observation in self.by_date.get(snapshot_date, []):
            latest_by_ticker[observation.ticker] = observation
        return list(latest_by_ticker.values())

    def list_all_by_date(self, snapshot_date):
        return list(self.by_date.get(snapshot_date, []))

    def list_canonical_by_date(self, snapshot_date):
        return [
            observation
            for observation in self.by_date.get(snapshot_date, [])
            if observation.config_hash
        ]

    def list_snapshot_dates(self):
        return sorted(self.by_date)


class FakeAccumulationScreenUseCase:
    """Fake RecordAccumulationObservationsUseCase — BackfillSignalObservationsUseCase
    depends on the explicit recorder, not the read-only screen use case directly."""

    def __init__(self, observations: FakeCandidateObservationsRepository):
        self.observations = observations
        self.requests = []
        self.effective_sessions = []
        self.recorded_contexts = []

    def execute(self, request, *, execution_context):
        self.requests.append(request)
        self.recorded_contexts.append(execution_context)
        effective_session = execution_context.effective_session
        self.effective_sessions.append(effective_session)
        recorded_count = 0
        for ticker in request.tickers:
            self.observations.append(ticker, request.as_of_date, request.window_days)
            recorded_count += 1
        response = AccumulationScreenResponse(
            candidates=[],
            screened_at=request.as_of_date,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=0,
            provider="test",
        )
        return RecordAccumulationObservationsResult(
            response=response, recorded_count=recorded_count
        )


class FakeAccumulationScreenUseCaseWithFingerprint:
    """Like FakeAccumulationScreenUseCase, but persists a sub_signal_fingerprint
    payload carrying the regime attribution sourced from request.market_context —
    mirroring the real AccumulationScreenUseCase._market_context_fingerprint()
    wiring closely enough to assert on it, without depending on the full
    production screener pipeline."""

    def __init__(self, observations: FakeCandidateObservationsRepository):
        self.observations = observations
        self.requests = []

    def execute(self, request, *, execution_context):
        self.requests.append(request)
        assert request.as_of_date is not None
        market_context = request.market_context
        fingerprint = {
            "market_regime_at_signal": (
                market_context.regime.value if market_context is not None else None
            ),
            "regime_confidence_at_signal": (
                market_context.regime_confidence if market_context is not None else None
            ),
            "regime_stability_at_signal": (
                market_context.regime_stability if market_context is not None else None
            ),
            "days_in_regime_at_signal": (
                market_context.days_in_regime if market_context is not None else None
            ),
        }
        recorded_count = 0
        for ticker in request.tickers:
            observations = self.observations.by_date.setdefault(request.as_of_date, [])
            observations.append(
                CandidateObservation(
                    ticker=ticker.upper(),
                    snapshot_date=request.as_of_date,
                    captured_at=datetime(2026, 7, 7, 12, 0, len(observations)),
                    payload={
                        "ticker": ticker.upper(),
                        "snapshot_date": request.as_of_date.isoformat(),
                        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                        "sub_signal_fingerprint": fingerprint,
                    },
                    window_sessions=7,
                    data_as_of_date=request.as_of_date,
                    config_hash="test-hash",
                )
            )
            recorded_count += 1
        response = AccumulationScreenResponse(
            candidates=[],
            screened_at=request.as_of_date,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=0,
            provider="test",
        )
        return RecordAccumulationObservationsResult(
            response=response, recorded_count=recorded_count
        )


def _observation_candidate(
    ticker: str, as_of: date, window_days: int, screen_result: str = "pass"
) -> AccumulationScreenObservationCandidate:
    """Build a real observation candidate with empty consumed-row provenance
    (all latest_*_date None), so AccumulationCandidateEvaluationResult's
    validation passes without dragging in the evaluator."""
    candidate = AccumulationCandidate(
        ticker=ticker.upper(),
        window_days=window_days,
        net_buy_days=0,
        total_days=0,
        net_buy_ratio=0.0,
        total_net_value=Decimal("0"),
        consecutive_streak=0,
        foreign_vwap=None,
        current_price=Decimal("100"),
        vwap_discount_pct=None,
        rsi=None,
        trend="SIDE",
        foreign_flow_score=0.0,
        top_brokers=None,
        institutional_flag=False,
    )
    evaluation_result = AccumulationCandidateEvaluationResult(
        candidate=candidate,
        consumed_candles=(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
        analysis_date=as_of,
    )
    return AccumulationScreenObservationCandidate(
        evaluation_result=evaluation_result,
        screen_result=screen_result,
        flow_evidence=None,
    )


class FakeReconcilingScreenUseCase:
    """Screen recorder fake that returns real observation_candidates for
    tickers with data and persists exactly those, so the capture-boundary
    rollup (evaluated/selected/unavailable) reconciles honestly with what is
    saved. Mirrors the production config (all reject gates off): every
    evaluated ticker is `pass`, so candidates == observation_candidates and no
    reject population is fabricated. `total_tickers_checked` is the full
    requested universe (as the real screen sets it), so unavailable = universe
    minus evaluated."""

    def __init__(
        self,
        observations: FakeCandidateObservationsRepository,
        *,
        unavailable: tuple[str, ...] = (),
        rejected: tuple[str, ...] = (),
    ):
        self.observations = observations
        self.unavailable = {ticker.upper() for ticker in unavailable}
        # Optional screen-rejected control tickers (DQ-003 Slice E). Evaluated
        # and persisted like everyone else, but classified screen_result !=
        # "pass", so they are NOT selected — modelling the non-production case
        # where a reject gate is active. Constructed at the DTO/use-case
        # boundary, not by faking the engine end-to-end.
        self.rejected = {ticker.upper() for ticker in rejected}
        self.requests = []

    def execute(self, request, *, execution_context):
        self.requests.append(request)
        evaluated = [
            ticker for ticker in request.tickers if ticker.upper() not in self.unavailable
        ]
        observation_candidates = [
            _observation_candidate(
                ticker,
                request.as_of_date,
                request.window_days,
                screen_result=(
                    "rejected_structural"
                    if ticker.upper() in self.rejected
                    else "pass"
                ),
            )
            for ticker in evaluated
        ]
        # Every evaluated ticker is persisted (pass + rejected alike), so
        # recorded_count == len(observation_candidates). Only `pass` candidates
        # are selected (survivors).
        recorded_count = 0
        for ticker in evaluated:
            self.observations.append(ticker, request.as_of_date, request.window_days)
            recorded_count += 1
        response = AccumulationScreenResponse(
            candidates=[
                oc.candidate
                for oc in observation_candidates
                if oc.screen_result == "pass"
            ],
            screened_at=request.as_of_date,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=len(request.tickers) - len(evaluated),
            provider="test",
            observation_candidates=observation_candidates,
        )
        return RecordAccumulationObservationsResult(
            response=response, recorded_count=recorded_count
        )


class FakeLabelGenerationUseCase:
    def __init__(self):
        self.requests = []

    def execute_all(self, request):
        self.requests.append(request)
        return GenerateAllSignalForwardLabelsResponse(
            observation_count=1,
            generated_count=1,
            unavailable_count=0,
            generated_dates=(request.signal_date,),
        )


class SpySignalForwardLabelsRepository:
    def __init__(self):
        self.saved = []

    def save_many(self, labels):
        self.saved.extend(labels)

    def get(self, ticker, signal_date, horizon):
        return None


class _GateOpenCalendar:
    """Gate-open, event-free calendar fake: the DQ-004 coverage gate passes and
    no corporate action is ever detected, so labels compute real outcomes."""

    def has_any_sync_marker(self, source="stockbit"):
        return True

    def get_events_for_ticker(
        self, ticker, from_date, to_date, event_types=None, as_of_fetched_at=None
    ):
        return []


def test_backfill_multi_window_generates_one_label_per_canonical_window():
    """S1 regression: windows=(7,30,90) with generate_labels=True must
    generate a label for every recorded canonical window observation — using
    the REAL GenerateSignalForwardLabelsUseCase, not a fake — guarding
    against silent collapse to latest-per-ticker via list_by_date()."""
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    candles = [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
    candles.extend(_candle("BBCA", signal_date + timedelta(days=i)) for i in range(1, 11))
    market = FakeMarketRepository(candles)
    labels_repo = SpySignalForwardLabelsRepository()
    real_label_use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
        corporate_action_calendar_repository=_GateOpenCalendar(),
    )

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=FakeAccumulationScreenUseCase(observations),
        screen_request_builder=_request_builder(),
        market_data_repository=market,
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
        label_generation_use_case=real_label_use_case,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            horizon=SignalLabelHorizon.SWING_10D,
            generate_labels=True,
            windows=(7, 30, 90),
        )
    )

    canonical = observations.list_canonical_by_date(signal_date)
    assert len(canonical) == 3
    assert {obs.window_sessions for obs in canonical} == {7, 30, 90}
    # One label attempted per canonical observation — not collapsed to 1.
    assert response.generated_label_count == len(canonical) == 3
    assert len(labels_repo.saved) == 3


def test_backfill_processes_eligible_dates_and_passes_as_of_date():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCase(observations)

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7, 30, 90),
        )
    )

    assert response.processed_date_count == 1
    assert response.saved_observation_count == 3
    assert [request.as_of_date for request in screen.requests] == [signal_date] * 3
    assert [request.window_days for request in screen.requests] == [7, 30, 90]
    assert screen.requests[0].bci_cluster_min_count == 4
    assert screen.requests[0].bci_stable_min_count == 2
    assert screen.requests[0].min_market_cap_idr == 500_000_000_000
    assert screen.requests[0].resistance_gate_enabled is False
    assert screen.requests[0].resistance_headroom_min_pct == 6.5
    assert screen.requests[0].ex_date_warning_days == 14
    assert screen.requests[0].sector_breadth_enabled is True
    assert screen.requests[0].sector_breadth_threshold == 0.7
    assert screen.requests[0].sector_breadth_bonus_pts == 8.0
    assert screen.requests[0].sector_breadth_min_tickers == 5
    assert screen.requests[0].min_foreign_flow_score_enabled is False
    assert screen.requests[0].min_signal_score_enabled is False


def test_backfill_skips_trading_date_without_target_source_candles():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCase(observations)

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository([_candle("IHSG", signal_date)]),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
        )
    )

    assert response.processed_date_count == 0
    assert response.skipped_dates[0].reason == "missing_source_candles_for_universe"
    assert screen.requests == []


def test_backfill_generates_labels_only_after_saved_observations_have_forward_window():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    labels = FakeLabelGenerationUseCase()
    candles = [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
    candles.extend(_candle("BBCA", signal_date + timedelta(days=i)) for i in range(1, 11))

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=FakeAccumulationScreenUseCase(observations),
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(candles),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
        label_generation_use_case=labels,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            horizon=SignalLabelHorizon.SWING_10D,
            generate_labels=True,
            windows=(7,),
        )
    )

    assert response.generated_label_count == 1
    assert response.unavailable_label_count == 0
    assert labels.requests[0].signal_date == signal_date
    assert labels.requests[0].horizons == (SignalLabelHorizon.SWING_10D,)


def test_backfill_does_not_generate_labels_without_enough_future_candles():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    labels = FakeLabelGenerationUseCase()
    candles = [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
    candles.extend(_candle("BBCA", signal_date + timedelta(days=i)) for i in range(1, 5))

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=FakeAccumulationScreenUseCase(observations),
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(candles),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
        label_generation_use_case=labels,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            horizon=SignalLabelHorizon.SWING_10D,
            generate_labels=True,
            windows=(7,),
        )
    )

    assert response.generated_label_count == 0
    assert response.skipped_dates[0].reason == "insufficient_future_candles_for_SWING_10D"
    assert labels.requests == []


def test_backfill_as_of_date_changes_per_historical_date():
    first_date = date(2026, 6, 1)
    second_date = date(2026, 6, 2)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCase(observations)

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [
                _candle("IHSG", first_date),
                _candle("IHSG", second_date),
                _candle("BBCA", first_date),
                _candle("BBCA", second_date),
            ]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=first_date,
            end_date=second_date,
            windows=(7,),
        )
    )

    assert response.processed_dates == (first_date, second_date)
    assert [request.as_of_date for request in screen.requests] == [first_date, second_date]


class RecordingMarketContextEvaluator:
    """Fake evaluate_market_context callable: records every as_of_date it is
    called with and returns a fixed MarketContext."""

    def __init__(self):
        self.calls: list[date] = []

    def __call__(self, *, as_of_date: date) -> MarketContext:
        self.calls.append(as_of_date)
        return MarketContext(
            regime=MarketRegime.RISK_ON,
            conviction=0.6,
            factors=(),
            signal_multiplier=1.0,
            gate_tightening=False,
            as_of_date=as_of_date,
            regime_confidence=0.8,
            regime_stability="STABLE",
            days_in_regime=6,
        )


class RaisingMarketContextEvaluator:
    """Fake evaluate_market_context callable that always fails."""

    def __init__(self):
        self.calls: list[date] = []

    def __call__(self, *, as_of_date: date) -> MarketContext:
        self.calls.append(as_of_date)
        raise RuntimeError("boom")


def test_backfill_evaluates_market_context_once_per_date_and_persists_regime_attribution():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCaseWithFingerprint(observations)
    evaluator = RecordingMarketContextEvaluator()

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
        evaluate_market_context=evaluator,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7, 30, 90),
        )
    )

    # Evaluated exactly once for the single trading date in range, not once per window.
    assert evaluator.calls == [signal_date]
    assert response.saved_observation_count == 3

    saved = observations.list_all_by_date(signal_date)
    assert len(saved) == 3
    for observation in saved:
        fingerprint = observation.payload["sub_signal_fingerprint"]
        assert fingerprint["market_regime_at_signal"] == MarketRegime.RISK_ON.value
        assert fingerprint["regime_confidence_at_signal"] == 0.8
        assert fingerprint["regime_stability_at_signal"] == "STABLE"
        assert fingerprint["days_in_regime_at_signal"] == 6


def test_backfill_uses_evidence_context_builder_for_source_availability():
    """Historical capture must not hardcode availability=None when a builder is wired."""
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCase(observations)
    sentinel_uc = object()
    builds: list[tuple] = []

    class _Builder:
        def build(self, *, effective_session, coverage_start, coverage_end):
            builds.append((coverage_start, coverage_end, effective_session))
            from src.application.dto.signal_evidence_execution_context import (
                SignalEvidenceExecutionContext,
            )

            return SignalEvidenceExecutionContext(
                effective_session=effective_session,
                source_availability_use_case=sentinel_uc,  # type: ignore[arg-type]
            )

    contexts: list = []

    class _RecordingScreen(FakeAccumulationScreenUseCase):
        def execute(self, request, *, execution_context):
            contexts.append(execution_context)
            return super().execute(request, execution_context=execution_context)

    screen = _RecordingScreen(observations)

    BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
        evidence_context_builder=_Builder(),  # type: ignore[arg-type]
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7,),
        )
    )

    assert len(builds) == 1
    assert len(contexts) == 1
    assert contexts[0].source_availability_use_case is sentinel_uc
    assert contexts[0].observation_contract == ACCUMULATION_DISCOVERY_CONTRACT
    assert contexts[0].semantic_compatibility_id == _LEAN_IDENTITY.semantic_compatibility_id


def test_backfill_market_context_failure_does_not_block_observations_but_notes_it():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCaseWithFingerprint(observations)
    evaluator = RaisingMarketContextEvaluator()

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
        evaluate_market_context=evaluator,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7, 30, 90),
        )
    )

    # Observations must still be generated — market_context failure is non-blocking.
    assert response.saved_observation_count == 3
    expected_note = f"market_context_unavailable_for_{signal_date.isoformat()}"
    assert any(expected_note in note for note in response.notes)

    saved = observations.list_all_by_date(signal_date)
    assert len(saved) == 3
    for observation in saved:
        fingerprint = observation.payload["sub_signal_fingerprint"]
        assert fingerprint["market_regime_at_signal"] is None
        assert fingerprint["regime_confidence_at_signal"] is None
        assert fingerprint["regime_stability_at_signal"] is None
        assert fingerprint["days_in_regime_at_signal"] is None


def test_backfill_resolves_one_deterministic_session_per_trading_date():
    """DQ-002E: exactly one EffectiveMarketSession per trading_date, shared
    across every window for that date — never resolved per ticker/window —
    and built from the deterministic after-close WIB decision timestamp."""
    first_date = date(2026, 6, 1)
    second_date = date(2026, 6, 2)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCase(observations)
    candles = [
        _candle("IHSG", first_date),
        _candle("IHSG", second_date),
        _candle("BBCA", first_date),
        _candle("BBCA", second_date),
    ]

    BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(candles),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=first_date,
            end_date=second_date,
            windows=(7, 30, 90),
        )
    )

    # 2 dates x 3 windows = 6 record() calls, but only 2 distinct contexts —
    # one resolve/builder call per date, reused across all windows for that date.
    assert len(screen.recorded_contexts) == 6
    assert all(ctx is not None for ctx in screen.recorded_contexts)
    first_date_contexts = screen.recorded_contexts[0:3]
    second_date_contexts = screen.recorded_contexts[3:6]

    # All windows receive the same context object by identity:
    assert first_date_contexts[0] is first_date_contexts[1]
    assert first_date_contexts[1] is first_date_contexts[2]

    assert second_date_contexts[0] is second_date_contexts[1]
    assert second_date_contexts[1] is second_date_contexts[2]

    # Different dates receive different context objects:
    assert first_date_contexts[0] is not second_date_contexts[0]

    # Their effective sessions have the corresponding deterministic dates:
    first_decision_at = first_date_contexts[0].effective_session.decision_at
    assert first_decision_at.date() == first_date
    assert first_decision_at.hour == 16 and first_decision_at.minute == 0

    second_decision_at = second_date_contexts[0].effective_session.decision_at
    assert second_decision_at.date() == second_date
    assert second_decision_at.hour == 16 and second_decision_at.minute == 0


def test_backfill_capture_counts_reconcile_with_saved_and_production_config():
    """DQ-003 Slice B: evaluated == saved (headline persistence cross-check),
    selected + rejected == evaluated, and under production-like config (all
    reject gates off) rejected == 0 and selected == evaluated. Empty membership
    source yields no survivorship note."""
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeReconcilingScreenUseCase(observations)

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [
                _candle("IHSG", signal_date),
                _candle("BBCA", signal_date),
                _candle("BBRI", signal_date),
            ]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA", "BBRI"),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7, 30, 90),
        )
    )

    assert response.universe_size == 2
    # 2 tickers x 3 windows evaluated, and every evaluated ticker is persisted.
    assert response.evaluated_count == 6
    assert response.evaluated_count == response.saved_observation_count
    # selected + rejected == evaluated (arithmetic invariant), rejected 0 today.
    assert response.selected_count + response.rejected_count == response.evaluated_count
    assert response.rejected_count == 0
    assert response.selected_count == response.evaluated_count
    assert response.unavailable_count == 0
    assert response.ticker_exclusions == ()
    # No @current membership source → no survivorship limitation.
    assert response.survivorship_limitation is None


def test_backfill_unavailable_universe_ticker_yields_exclusion_and_count():
    """DQ-003 Slice B (criterion 12): a universe ticker with no source input is
    never evaluated, so it appears once per processed date in ticker_exclusions
    with a machine-readable reason and inflates unavailable_count per window."""
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeReconcilingScreenUseCase(observations, unavailable=("GOTO",))

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA", "GOTO"),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7, 30),
        )
    )

    assert response.universe_size == 2
    # Only BBCA evaluated across both windows; GOTO unavailable every window.
    assert response.evaluated_count == 2
    assert response.evaluated_count == response.saved_observation_count
    assert response.unavailable_count == 2  # 2 windows x (universe 2 - evaluated 1)
    # Exclusion is deduped per date, not per window.
    assert len(response.ticker_exclusions) == 1
    exclusion = response.ticker_exclusions[0]
    assert exclusion.ticker == "GOTO"
    assert exclusion.date == signal_date
    assert exclusion.reason == "source_unavailable_not_evaluated"


def test_backfill_current_universe_membership_surfaces_survivorship_and_dict_keys():
    """DQ-003 Slice B (criterion 13): a `@current` membership source carries the
    survivorship limitation, and every new reporting key is present in
    to_dict() with ticker_exclusions serialized as dicts."""
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeReconcilingScreenUseCase(observations, unavailable=("GOTO",))

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA", "GOTO"),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7,),
            universe_membership_source="lq45@current",
        )
    )

    assert response.universe_membership_source == "lq45@current"
    assert response.survivorship_limitation is not None

    payload = response.to_dict()
    for key in (
        "universe_size",
        "evaluated_count",
        "selected_count",
        "rejected_count",
        "unavailable_count",
        "universe_membership_source",
        "survivorship_limitation",
        "ticker_exclusions",
    ):
        assert key in payload
    assert payload["universe_membership_source"] == "lq45@current"
    assert payload["survivorship_limitation"] is not None
    assert payload["ticker_exclusions"] == [
        {
            "date": signal_date.isoformat(),
            "ticker": "GOTO",
            "reason": "source_unavailable_not_evaluated",
        }
    ]


def test_backfill_production_config_is_candidate_only_and_ineligible_for_recall():
    """DQ-003 Slice E (criterion 11): under the production-like path every
    evaluated ticker is `pass` (no reject gate), so there is no screen-rejected
    control. `contains_control_population` is False and `recall_eligibility`
    states the machine-readable ineligibility reason — both in the response and
    in to_dict()."""
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeReconcilingScreenUseCase(observations)

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA",),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7,),
        )
    )

    assert response.rejected_count == 0
    assert response.contains_control_population is False
    assert (
        response.recall_eligibility
        == "ineligible_candidate_only_no_screen_rejected_control"
    )

    payload = response.to_dict()
    assert payload["contains_control_population"] is False
    assert (
        payload["recall_eligibility"]
        == "ineligible_candidate_only_no_screen_rejected_control"
    )


def test_backfill_with_screen_rejected_control_is_eligible():
    """DQ-003 Slice E: when a run persists at least one screen-rejected
    observation (screen_result != "pass"), `contains_control_population` is True
    and eligibility flips. This proves the marker tracks real screen results, not
    a hardcoded False. The reject is constructed at the DTO/use-case boundary."""
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeReconcilingScreenUseCase(observations, rejected=("GOTO",))

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [
                _candle("IHSG", signal_date),
                _candle("BBCA", signal_date),
                _candle("GOTO", signal_date),
            ]
        ),
        candidate_observations_repository=observations,
        observation_identity=_LEAN_IDENTITY,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("BBCA", "GOTO"),
            start_date=signal_date,
            end_date=signal_date,
            windows=(7,),
        )
    )

    # GOTO evaluated but rejected; BBCA evaluated and selected.
    assert response.evaluated_count == 2
    assert response.selected_count == 1
    assert response.rejected_count == 1
    assert response.contains_control_population is True
    assert (
        response.recall_eligibility == "eligible_contains_screen_rejected_control"
    )
    assert response.to_dict()["contains_control_population"] is True


def _request_builder() -> BuildSignalObservationScreenRequest:
    return BuildSignalObservationScreenRequest(
        min_net_buy_days=1,
        min_foreign_flow_score=0.0,
        min_foreign_flow_score_enabled=False,
        min_signal_score=0.0,
        min_signal_score_enabled=False,
        min_piotroski=6,
        tier1_broker_codes=frozenset({"AK", "BK"}),
        bci_cluster_min_count=4,
        bci_stable_min_count=2,
        min_market_cap_idr=500_000_000_000,
        resistance_gate_enabled=False,
        resistance_headroom_min_pct=6.5,
        ex_date_warning_days=14,
        sector_breadth_enabled=True,
        sector_breadth_threshold=0.7,
        sector_breadth_bonus_pts=8.0,
        sector_breadth_min_tickers=5,
        strategy_name="williams-r-bounce",
    )


def _candle(ticker: str, candle_date: date) -> Candle:
    return Candle(
        ticker=ticker,
        date=candle_date,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=1000,
    )
