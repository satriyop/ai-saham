from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenResponse,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsRequest,
    BackfillSignalObservationsUseCase,
)
from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateAllSignalForwardLabelsResponse,
)
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.market_context import MarketContext, MarketRegime
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

    def append(self, ticker: str, snapshot_date: date) -> None:
        observations = self.by_date.setdefault(snapshot_date, [])
        observations.append(
            CandidateObservation(
                ticker=ticker.upper(),
                snapshot_date=snapshot_date,
                captured_at=datetime(2026, 7, 7, 12, 0, len(observations)),
                payload={"ticker": ticker.upper(), "snapshot_date": snapshot_date.isoformat()},
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

    def list_snapshot_dates(self):
        return sorted(self.by_date)


class FakeAccumulationScreenUseCase:
    def __init__(self, observations: FakeCandidateObservationsRepository):
        self.observations = observations
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        assert request.as_of_date is not None
        for ticker in request.tickers:
            self.observations.append(ticker, request.as_of_date)
        return AccumulationScreenResponse(
            candidates=[],
            screened_at=request.as_of_date,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=0,
            provider="test",
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

    def execute(self, request):
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
                        "sub_signal_fingerprint": fingerprint,
                    },
                )
            )
        return AccumulationScreenResponse(
            candidates=[],
            screened_at=request.as_of_date,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=0,
            provider="test",
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


def test_backfill_processes_eligible_dates_and_passes_as_of_date():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCase(observations)

    response = BackfillSignalObservationsUseCase(
        accumulation_screen_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
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
        accumulation_screen_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository([_candle("IHSG", signal_date)]),
        candidate_observations_repository=observations,
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
        accumulation_screen_use_case=FakeAccumulationScreenUseCase(observations),
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(candles),
        candidate_observations_repository=observations,
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
        accumulation_screen_use_case=FakeAccumulationScreenUseCase(observations),
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(candles),
        candidate_observations_repository=observations,
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
        accumulation_screen_use_case=screen,
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
        accumulation_screen_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
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


def test_backfill_market_context_failure_does_not_block_observations_but_notes_it():
    signal_date = date(2026, 6, 1)
    observations = FakeCandidateObservationsRepository()
    screen = FakeAccumulationScreenUseCaseWithFingerprint(observations)
    evaluator = RaisingMarketContextEvaluator()

    response = BackfillSignalObservationsUseCase(
        accumulation_screen_use_case=screen,
        screen_request_builder=_request_builder(),
        market_data_repository=FakeMarketRepository(
            [_candle("IHSG", signal_date), _candle("BBCA", signal_date)]
        ),
        candidate_observations_repository=observations,
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
