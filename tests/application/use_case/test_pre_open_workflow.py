"""Tests for pre-open workflow orchestration."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.use_case.pre_open_screen_use_case import (
    PreOpenScreenConfig,
    PreOpenScreenResponse,
)
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenWorkflowRequest,
    PreOpenWorkflowUseCase,
)
from src.domain.value_objects.screener_result import (
    MoverData,
    PreOpenScreenResult,
    ScreenerCandidate,
)


class FakeScreenUseCase:
    def __init__(self, response: PreOpenScreenResponse) -> None:
        self.response = response
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.response


class FakeMarketRepository:
    def __init__(self, ranges: dict[str, tuple[date, date] | None]) -> None:
        self.ranges = ranges

    def get_date_range(self, ticker: str):
        return self.ranges.get(ticker)


class FakeBrokerRepository:
    def __init__(self, ranges: dict[str, tuple[date, date] | None]) -> None:
        self.ranges = ranges

    def get_date_range(self, ticker: str, source=None):
        return self.ranges.get(ticker)


def _candidate(ticker: str = "BBCA") -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        iev=150_000,
        entry_price=Decimal("1000"),
        stop_loss_price=Decimal("950"),
        capital=Decimal("3000000"),
        trend_signal="BULLISH",
    )


def _screen_response(
    screened_date: date,
    candidates: list[ScreenerCandidate] | None = None,
    warnings: list[str] | None = None,
) -> PreOpenScreenResponse:
    return PreOpenScreenResponse(
        result=PreOpenScreenResult(
            screened_date=screened_date,
            iev_min=100_000,
            total_movers_seen=1,
            candidates=candidates or [_candidate()],
        ),
        warnings=warnings or [],
        raw_movers=[MoverData("BBCA", 150_000)],
    )


def test_pre_open_workflow_executes_screen_and_builds_freshness():
    run_date = date(2026, 6, 18)
    screen = FakeScreenUseCase(_screen_response(run_date))
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        broker_repository=FakeBrokerRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        registry=object(),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
        )
    )

    assert screen.requests[0].run_date == run_date
    assert response.result.candidates[0].ticker == "BBCA"
    assert response.raw_movers[0].ticker == "BBCA"
    assert response.data_freshness.candle_end == run_date
    assert response.data_freshness.broker_end == run_date
    assert response.warnings == []


def test_pre_open_workflow_propagates_warnings_and_stale_data_notes():
    run_date = date(2026, 6, 18)
    screen = FakeScreenUseCase(
        _screen_response(run_date, warnings=["screen warning"])
    )
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({"BBCA": (date(2026, 1, 1), date(2026, 6, 17))}),
        broker_repository=FakeBrokerRepository({"BBCA": None}),
        registry=object(),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            guard_warnings=("guard warning",),
        )
    )

    assert response.warnings == ["screen warning", "guard warning"]
    assert "Latest candle date is 2026-06-17" in response.data_freshness.warnings[0]
    assert "No cached broker-flow date" in response.data_freshness.warnings[1]


def test_pre_open_workflow_uses_oldest_latest_date_across_candidates():
    run_date = date(2026, 6, 13)
    screen = FakeScreenUseCase(
        _screen_response(
            run_date,
            candidates=[_candidate("BBCA"), _candidate("BUMI")],
        )
    )
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository(
            {
                "BBCA": (date(2026, 1, 1), date(2026, 6, 12)),
                "BUMI": (date(2026, 1, 1), date(2026, 6, 10)),
            }
        ),
        broker_repository=FakeBrokerRepository(
            {
                "BBCA": (date(2026, 1, 1), date(2026, 6, 12)),
                "BUMI": (date(2026, 1, 1), date(2026, 6, 11)),
            }
        ),
        registry=object(),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
        )
    )

    assert response.data_freshness.analysis_date == run_date
    assert response.data_freshness.candle_end == date(2026, 6, 10)
    assert response.data_freshness.broker_end == date(2026, 6, 11)
    assert any("Latest candle" in warning for warning in response.data_freshness.warnings)
    assert any("Latest broker-flow" in warning for warning in response.data_freshness.warnings)
    assert any("differ" in warning for warning in response.data_freshness.warnings)


def test_pre_open_workflow_reports_market_regime_failure_as_warning():
    run_date = date(2026, 6, 18)
    screen = FakeScreenUseCase(_screen_response(run_date))
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        broker_repository=FakeBrokerRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        registry=object(),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            with_regime=True,
            regime_universe="missing",
            db_path=Path("/tmp/does-not-exist.db"),
        )
    )

    assert response.market_regime is None
    assert any(warning.startswith("Market regime unavailable:") for warning in response.warnings)
