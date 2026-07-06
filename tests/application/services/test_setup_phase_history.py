from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.setup_phase_history import load_previous_setup_phases
from src.application.services.setup_phase_detector import SetupPhaseDetector
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.domain.value_objects.setup_phase import SetupPhaseState


class FakeCandidateObservationsRepository:
    def __init__(self, observations):
        self.observations = observations
        self.calls = []

    def save_many(self, observations):
        raise AssertionError("not used")

    def get_latest(self, ticker, snapshot_date):
        raise AssertionError("not used")

    def get_at(self, ticker, snapshot_date, captured_at):
        raise AssertionError("not used")

    def list_recent(self, ticker, *, before_date=None, limit=20):
        self.calls.append((ticker, before_date, limit))
        return list(reversed(self.observations))[:limit]


def _observation(
    day: date,
    phase: str | None,
    setup_family: str | None = "accumulation",
    workflow: str = "screen_accum",
):
    fingerprint = {
        "setup_family": setup_family,
        "setup_phase_current": phase,
    }
    return CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(day.year, day.month, day.day, 9, 0, 0),
        payload={
            "schema_version": 1,
            "workflow": workflow,
            "sub_signal_fingerprint": fingerprint,
        },
    )


def test_load_previous_setup_phases_returns_oldest_to_newest():
    repo = FakeCandidateObservationsRepository(
        [
            _observation(date(2026, 7, 1), "ACCUMULATION"),
            _observation(date(2026, 7, 2), "COMPRESSION"),
        ]
    )

    phases = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 3),
        setup_family="accumulation",
    )

    assert phases == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
    )
    assert repo.calls == [("BBCA", date(2026, 7, 3), 20)]


def test_load_previous_setup_phases_ignores_other_setup_families_and_bad_values():
    repo = FakeCandidateObservationsRepository(
        [
            _observation(date(2026, 7, 1), "ACCUMULATION", "other"),
            _observation(date(2026, 7, 2), "NOT_A_PHASE", "accumulation"),
            _observation(date(2026, 7, 3), "COMPRESSION", "accumulation"),
        ]
    )

    phases = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 4),
        setup_family="accumulation",
    )

    assert phases == (SetupPhaseState.COMPRESSION,)


def test_generic_history_only_feeds_accumulation_compatibility_path():
    repo = FakeCandidateObservationsRepository(
        [
            _observation(date(2026, 7, 1), "ACCUMULATION", None, "screen_accum"),
            _observation(date(2026, 7, 2), "COMPRESSION", None, "screen_accum"),
        ]
    )

    accumulation = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 3),
        setup_family="foreign-bounce",
    )
    pullback = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 3),
        setup_family="pullback-continuation",
    )
    breakout = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 3),
        setup_family="coiled-spring",
    )

    assert accumulation == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
    )
    assert pullback == ()
    assert breakout == ()


def test_saved_observations_make_day_n_plus_2_breakout_sequence_valid(tmp_path):
    repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    breakout_day = date(2026, 7, 3)

    without_history = SetupPhaseDetector().detect(
        candles=_breakout_candles(),
        setup_eval=None,
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow_evidence(),
        setup_family="accumulation",
    )
    assert without_history.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert without_history.sequence_valid is False

    repo.save_many(
        [
            _observation(date(2026, 7, 1), "ACCUMULATION"),
            _observation(date(2026, 7, 2), "COMPRESSION"),
        ]
    )
    previous_phases = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=breakout_day,
        setup_family="accumulation",
    )
    with_history = SetupPhaseDetector().detect(
        candles=_breakout_candles(),
        setup_eval=None,
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow_evidence(),
        setup_family="accumulation",
        previous_phases=previous_phases,
    )

    assert previous_phases == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
    )
    assert with_history.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert with_history.sequence_valid is True


def _breakout_candles() -> list[Candle]:
    candles = []
    for idx in range(20):
        close = Decimal("100")
        high = Decimal("101")
        open_ = Decimal("99")
        volume = 1_000 if idx < 15 else 2_000
        if idx == 19:
            open_ = Decimal("101")
            close = Decimal("105")
            high = Decimal("106")
        candles.append(
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 10 + idx),
                open=open_,
                high=high,
                low=Decimal("98"),
                close=close,
                volume=volume,
            )
        )
    return candles


def _setup_evidence():
    return SimpleNamespace(
        rsi=55.0,
        bb_width_pctile=0.15,
        vwap_pct=1.0,
        match_strength=100.0,
        rs_freshness=None,
        rs_vs_ihsg_5d=None,
        candle_source="stockbit",
    )


def _flow_evidence():
    return SimpleNamespace(
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=2,
    )
