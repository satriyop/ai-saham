"""Tests for SaveScreenWatchlistUseCase."""

from datetime import date
from decimal import Decimal
from typing import Any

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.assess_signal import AssessSignalResponse
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistRequest,
    SaveScreenWatchlistUseCase,
)
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry
from src.domain.value_objects.signal_assessment import (
    ACCUMULATION_DISCOVERY_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)


class FakeWatchlistRepository:
    """In-memory fake that records saved entries."""

    def __init__(self) -> None:
        self.saved: list[ScreenSnapshotEntry] = []

    def save_snapshot(self, entries: list[ScreenSnapshotEntry]) -> None:
        self.saved = list(entries)


def _candidate(**overrides: Any) -> AccumulationCandidate:
    values = {
        "ticker": "BBCA",
        "window_days": 7,
        "net_buy_days": 5,
        "total_days": 7,
        "net_buy_ratio": 5 / 7,
        "total_net_value": Decimal("10000000000"),
        "consecutive_streak": 3,
        "foreign_vwap": Decimal("1030"),
        "current_price": Decimal("1000"),
        "vwap_discount_pct": 3.0,
        "rsi": 55.0,
        "trend": "SIDE",
        "accum_score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def _signal_assessment(score: int = 65) -> AssessSignalResponse:
    return AssessSignalResponse(
        ticker="BBCA",
        assessment=SignalAssessment(
            identity=ACCUMULATION_DISCOVERY_IDENTITY,
            ticker="BBCA",
            score=score,
            strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH,
            breakdown=(("factor_a", 50.0),),
            rationale=("decent",),
            snapshot_date=date(2026, 6, 28),
            signal_authority_coverage=None,
        ),
    )


def test_save_creates_entries_with_correct_fields() -> None:
    repo = FakeWatchlistRepository()
    use_case = SaveScreenWatchlistUseCase(repo)

    candidates = [
        _candidate(ticker="BBCA", accum_score=80.0, consecutive_streak=5,
                   net_buy_ratio=0.8, bci_label="CLUSTER",
                   signal_assessment=_signal_assessment(72)),
        _candidate(ticker="BBRI", accum_score=65.0, consecutive_streak=3,
                   net_buy_ratio=0.6, bci_label="STABLE"),
    ]

    use_case.execute(SaveScreenWatchlistRequest(
        name="test-watch",
        candidates=candidates,
        universe="lq45",
        window_days=7,
    ))

    assert len(repo.saved) == 2

    e1 = repo.saved[0]
    assert e1.name == "test-watch"
    assert e1.ticker == "BBCA"
    assert e1.rank == 1
    assert e1.universe == "lq45"
    assert e1.window_days == 7
    assert e1.accum_score == 80.0
    assert e1.signal_score == 72
    assert e1.consecutive_streak == 5
    assert e1.net_buy_ratio == 0.8
    assert e1.bci_label == "CLUSTER"

    e2 = repo.saved[1]
    assert e2.ticker == "BBRI"
    assert e2.rank == 2
    assert e2.accum_score == 65.0
    assert e2.signal_score is None


def test_save_rank_starts_at_one() -> None:
    repo = FakeWatchlistRepository()
    use_case = SaveScreenWatchlistUseCase(repo)

    candidates = [
        _candidate(ticker="A"),
        _candidate(ticker="B"),
        _candidate(ticker="C"),
    ]

    use_case.execute(SaveScreenWatchlistRequest(
        name="ranks",
        candidates=candidates,
        universe="test",
        window_days=7,
    ))

    assert repo.saved[0].rank == 1
    assert repo.saved[1].rank == 2
    assert repo.saved[2].rank == 3


def test_save_returns_saved_count_and_name() -> None:
    repo = FakeWatchlistRepository()
    use_case = SaveScreenWatchlistUseCase(repo)

    result = use_case.execute(SaveScreenWatchlistRequest(
        name="my-watch",
        candidates=[_candidate(ticker="BBCA")],
        universe="lq45",
        window_days=30,
    ))

    assert result.saved_count == 1
    assert result.name == "my-watch"


def test_signal_score_none_when_no_signal_assessment() -> None:
    repo = FakeWatchlistRepository()
    use_case = SaveScreenWatchlistUseCase(repo)

    candidates = [
        _candidate(ticker="BBCA", signal_assessment=None),
    ]

    use_case.execute(SaveScreenWatchlistRequest(
        name="no-signal",
        candidates=candidates,
        universe="test",
        window_days=7,
    ))

    assert repo.saved[0].signal_score is None
