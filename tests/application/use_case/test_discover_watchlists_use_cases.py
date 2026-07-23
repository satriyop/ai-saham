"""Tests for ListScreenWatchlistsUseCase and CompareScreenWatchlistUseCase.

Layer: Application
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.screen_accum_result_projector import (
    ScreenAccumSingleProjection,
)
from src.application.use_case.compare_screen_watchlist_use_case import (
    CompareScreenWatchlistRequest,
    CompareScreenWatchlistResult,
    CompareScreenWatchlistUseCase,
    WatchlistNotFoundError,
)
from src.application.use_case.list_screen_watchlists_use_case import (
    ListScreenWatchlistsRequest,
    ListScreenWatchlistsResult,
    ListScreenWatchlistsUseCase,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
    RunAccumulationScreenWorkflowUseCase,
)
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


def test_list_screen_watchlists_use_case() -> None:
    now = datetime(2026, 7, 21, 10, 0)
    repo = MagicMock()
    repo.list_snapshots.return_value = [
        {
            "name": "my_shortlist",
            "latest_saved_at": now.isoformat(),
            "universe": "lq45",
            "window_days": 7,
            "ticker_count": 2,
        }
    ]
    repo.get_latest_snapshot.return_value = [
        ScreenSnapshotEntry(
            name="my_shortlist",
            saved_at=now,
            universe="lq45",
            window_days=7,
            ticker="BBRI",
            rank=1,
            accum_score=80.0,
            signal_score=75.0,
            consecutive_streak=3,
            net_buy_ratio=0.15,
            bci_label="ACCUMULATION",
        ),
    ]

    use_case = ListScreenWatchlistsUseCase(repo)
    result = use_case.execute(ListScreenWatchlistsRequest(name="my_shortlist"))

    assert isinstance(result, ListScreenWatchlistsResult)
    assert len(result.summaries) == 1
    assert result.summaries[0].name == "my_shortlist"
    assert len(result.selected_entries) == 1
    assert result.selected_entries[0].ticker == "BBRI"


def test_compare_screen_watchlist_use_case_success() -> None:
    now = datetime(2026, 7, 21, 10, 0)
    repo = MagicMock()
    repo.get_latest_snapshot.return_value = [
        ScreenSnapshotEntry(
            name="my_shortlist",
            saved_at=now,
            universe="lq45",
            window_days=7,
            ticker="BBRI",
            rank=1,
            accum_score=80.0,
            signal_score=75.0,
            consecutive_streak=3,
            net_buy_ratio=0.15,
            bci_label="ACCUMULATION",
        ),
        ScreenSnapshotEntry(
            name="my_shortlist",
            saved_at=now,
            universe="lq45",
            window_days=7,
            ticker="BMRI",
            rank=2,
            accum_score=70.0,
            signal_score=65.0,
            consecutive_streak=2,
            net_buy_ratio=0.10,
            bci_label="ACCUMULATION",
        ),
    ]

    cand1 = MagicMock(spec=AccumulationCandidate)
    cand1.ticker = "BBRI"
    cand1.accum_score = 85.0
    cand1.signal_assessment = None

    cand2 = MagicMock(spec=AccumulationCandidate)
    cand2.ticker = "BBNI"  # New candidate!
    cand2.accum_score = 65.0
    cand2.signal_assessment = None

    fresh_proj = MagicMock(spec=ScreenAccumSingleProjection)
    fresh_proj.candidates = [cand1, cand2]

    workflow = MagicMock(spec=RunAccumulationScreenWorkflowUseCase)
    workflow.execute.return_value = fresh_proj

    use_case = CompareScreenWatchlistUseCase(
        watchlist_repository=repo,
        screen_workflow_use_case=workflow,
    )

    req = CompareScreenWatchlistRequest(
        name="my_shortlist",
        screen_request=MagicMock(spec=RunAccumulationScreenWorkflowRequest),
    )

    result = use_case.execute(req)

    assert isinstance(result, CompareScreenWatchlistResult)
    assert result.comparison.snapshot_name == "my_shortlist"
    assert "BBNI" in result.comparison.new_tickers
    assert "BMRI" in result.comparison.dropped_tickers


def test_compare_screen_watchlist_not_found_raises() -> None:
    repo = MagicMock()
    repo.get_latest_snapshot.return_value = []
    workflow = MagicMock()

    use_case = CompareScreenWatchlistUseCase(repo, workflow)

    req = CompareScreenWatchlistRequest(
        name="missing",
        screen_request=MagicMock(spec=RunAccumulationScreenWorkflowRequest),
    )

    with pytest.raises(WatchlistNotFoundError):
        use_case.execute(req)
