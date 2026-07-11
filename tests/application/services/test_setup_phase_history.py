from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.setup_phase_detector import SetupPhaseDetector
from src.application.services.setup_phase_history import load_previous_setup_phases
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)


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


def test_generic_history_feeds_accumulation_compatibility_path():
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

    assert accumulation == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
    )
    # pullback-continuation's required_sequence is [] (config), so generic
    # screen history is not needed/whitelisted for it.
    assert pullback == ()


def test_generic_compression_history_feeds_coiled_spring_breakout_family():
    """screen accum is the only workflow that persists lifecycle-phase
    observations (analyze swing never writes them, only reads). Without
    generic COMPRESSION history flowing into breakout/coiled-spring, their
    required_sequence=[COMPRESSION, BREAKOUT_CONFIRMATION] could never be
    satisfied from normal use."""
    repo = FakeCandidateObservationsRepository(
        [
            _observation(date(2026, 7, 1), "ACCUMULATION", None, "screen_accum"),
            _observation(date(2026, 7, 2), "COMPRESSION", None, "screen_accum"),
        ]
    )

    breakout = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 3),
        setup_family="coiled-spring",
    )

    # Only the COMPRESSION observation is accepted generically — a generic
    # screen scan reaching ACCUMULATION (or, symmetrically, a generic scan
    # reaching BREAKOUT_CONFIRMATION) must not count as validated history for
    # a specific named setup's entry sequence.
    assert breakout == (SetupPhaseState.COMPRESSION,)


def test_generic_non_compression_history_does_not_feed_coiled_spring_breakout_family():
    repo = FakeCandidateObservationsRepository(
        [
            _observation(date(2026, 7, 1), "ACCUMULATION", None, "screen_accum"),
            _observation(date(2026, 7, 2), "BREAKOUT_CONFIRMATION", None, "screen_accum"),
        ]
    )

    breakout = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 3),
        setup_family="coiled-spring",
    )

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
    """21 sessions matching VolumeTriggerValidityConfig defaults (Point 3):
    15 reference sessions + 5 dry-up sessions (volume <= 50% of reference) +
    1 standalone expansion/breakout session (volume >= 150% of dry-up avg,
    positive close) — the only shape that confirms volume_trigger_confirmed.
    """
    candles = []
    for idx in range(21):
        close = Decimal("100")
        high = Decimal("101")
        open_ = Decimal("99")
        if idx < 15:
            volume = 2_000  # reference/baseline window
        elif idx < 20:
            volume = 800  # dry-up window: 800/2000 = 0.4 <= dry_up_max_ratio 0.50
        else:
            volume = 2_400  # expansion session: 2400/800 = 3.0 >= expansion_min_ratio 1.50
        if idx == 20:
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
