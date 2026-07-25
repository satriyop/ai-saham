"""Tests for pre-open workflow orchestration."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.use_case.pre_open_screen_use_case import (
    PreOpenScreenConfig,
    PreOpenScreenResponse,
)
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenSnapshotScreenResult,
    PreOpenWorkflowRequest,
    PreOpenWorkflowUseCase,
)
from src.domain.ports.browser_data_provider import (
    BrowserDataProviderError,
    BrowserInteractionRequired,
)
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
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


class RaisingScreenUseCase:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        raise self.exc


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
        evaluate_market_context=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            regime_enabled=True,
            regime_universe="missing",
            db_path=Path("/tmp/does-not-exist.db"),
        )
    )

    assert response.market_regime is None
    assert any(warning.startswith("Market regime unavailable:") for warning in response.warnings)


def test_pre_open_workflow_uses_injected_market_context_evaluator():
    run_date = date(2026, 6, 18)
    calls: list[dict] = []
    screen = FakeScreenUseCase(_screen_response(run_date))
    expected_context = object()
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        broker_repository=FakeBrokerRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        evaluate_market_context=lambda **kwargs: calls.append(kwargs) or expected_context,
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            regime_enabled=True,
            regime_universe="idx80",
            benchmark="^JKSE",
            db_path=Path("/tmp/test.db"),
        )
    )

    assert response.market_regime is expected_context
    assert calls == [
        {
            "db_path": Path("/tmp/test.db"),
            "as_of_date": run_date,
            "universe": "idx80",
            "benchmark": "IHSG",
        }
    ]


def test_pre_open_workflow_reports_live_success_when_movers_seen():
    run_date = date(2026, 6, 18)
    screen = FakeScreenUseCase(_screen_response(run_date))
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        broker_repository=FakeBrokerRepository({"BBCA": (date(2026, 1, 1), run_date)}),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(config=PreOpenScreenConfig(fast_mode=True), run_date=run_date)
    )

    assert response.source_status == PreOpenSourceStatus.LIVE_SUCCESS
    assert response.source_message is None


def test_pre_open_workflow_reports_empty_confirmed_when_zero_movers_seen():
    run_date = date(2026, 6, 18)
    screen_response = PreOpenScreenResponse(
        result=PreOpenScreenResult(
            screened_date=run_date,
            iev_min=100_000,
            total_movers_seen=0,
            candidates=[],
        ),
        warnings=[],
        raw_movers=[],
    )
    screen = FakeScreenUseCase(screen_response)
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({}),
        broker_repository=FakeBrokerRepository({}),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(config=PreOpenScreenConfig(fast_mode=True), run_date=run_date)
    )

    assert response.source_status == PreOpenSourceStatus.EMPTY_CONFIRMED
    assert response.result.candidates == []
    assert response.source_message is not None


def test_pre_open_workflow_does_not_treat_filtered_zero_candidates_as_empty_confirmed():
    """total_movers_seen > 0 but every mover was filtered out -> still LIVE_SUCCESS."""
    run_date = date(2026, 6, 18)
    screen_response = PreOpenScreenResponse(
        result=PreOpenScreenResult(
            screened_date=run_date,
            iev_min=100_000,
            total_movers_seen=5,
            candidates=[],
        ),
        warnings=[],
        raw_movers=[MoverData("BBCA", 150_000)],
    )
    screen = FakeScreenUseCase(screen_response)
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({}),
        broker_repository=FakeBrokerRepository({}),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(config=PreOpenScreenConfig(fast_mode=True), run_date=run_date)
    )

    assert response.source_status == PreOpenSourceStatus.LIVE_SUCCESS


def test_pre_open_workflow_reports_unavailable_on_provider_error():
    run_date = date(2026, 6, 18)
    screen = RaisingScreenUseCase(BrowserDataProviderError("connection reset"))
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({}),
        broker_repository=FakeBrokerRepository({}),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(config=PreOpenScreenConfig(fast_mode=True), run_date=run_date)
    )

    assert response.source_status == PreOpenSourceStatus.UNAVAILABLE
    assert "connection reset" in response.source_message
    assert response.result.candidates == []


def test_pre_open_workflow_reraises_browser_interaction_required():
    run_date = date(2026, 6, 18)
    screen = RaisingScreenUseCase(
        BrowserInteractionRequired(url="https://stockbit.com", instructions="log in")
    )
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({}),
        broker_repository=FakeBrokerRepository({}),
    )

    with pytest.raises(BrowserInteractionRequired):
        workflow.execute(
            PreOpenWorkflowRequest(config=PreOpenScreenConfig(fast_mode=True), run_date=run_date)
        )


def test_pre_open_workflow_outside_window_skips_live_fetch():
    run_date = date(2026, 6, 18)
    screen = FakeScreenUseCase(_screen_response(run_date))
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({}),
        broker_repository=FakeBrokerRepository({}),
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            outside_window=True,
        )
    )

    assert screen.requests == []
    assert response.source_status == PreOpenSourceStatus.OUTSIDE_WINDOW
    assert response.result.candidates == []
    assert response.source_message is not None


def test_pre_open_workflow_outside_window_with_snapshot_returns_snapshot_success():
    run_date = date(2026, 6, 18)
    snapshot_date = date(2026, 6, 17)
    live_screen = FakeScreenUseCase(_screen_response(run_date))

    snapshot_calls: list[tuple] = []

    def _run_snapshot_screen(config, as_of_date):
        snapshot_calls.append((config, as_of_date))
        return PreOpenSnapshotScreenResult(
            snapshot_date=snapshot_date,
            response=_screen_response(snapshot_date, candidates=[_candidate("BUMI")]),
        )

    workflow = PreOpenWorkflowUseCase(
        screen_use_case=live_screen,
        market_repository=FakeMarketRepository({"BUMI": (date(2026, 1, 1), snapshot_date)}),
        broker_repository=FakeBrokerRepository({"BUMI": (date(2026, 1, 1), snapshot_date)}),
        run_snapshot_screen=_run_snapshot_screen,
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            outside_window=True,
        )
    )

    assert live_screen.requests == []
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0][1] == run_date
    assert response.source_status == PreOpenSourceStatus.SNAPSHOT_SUCCESS
    assert response.result.candidates[0].ticker == "BUMI"
    assert response.source_snapshot_ref == snapshot_date.isoformat()
    # source_snapshot_ref is a DB snapshot identifier (an ISO date here), not a filesystem path.
    assert date.fromisoformat(response.source_snapshot_ref) == snapshot_date
    assert response.source_message is not None
    assert snapshot_date.isoformat() in response.source_message


def test_pre_open_workflow_outside_window_no_snapshot_falls_back_to_outside_window():
    run_date = date(2026, 6, 18)
    live_screen = FakeScreenUseCase(_screen_response(run_date))

    def _run_snapshot_screen(config, as_of_date):
        return None

    workflow = PreOpenWorkflowUseCase(
        screen_use_case=live_screen,
        market_repository=FakeMarketRepository({}),
        broker_repository=FakeBrokerRepository({}),
        run_snapshot_screen=_run_snapshot_screen,
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            outside_window=True,
        )
    )

    assert live_screen.requests == []
    assert response.source_status == PreOpenSourceStatus.OUTSIDE_WINDOW
    assert response.result.candidates == []


def test_pre_open_workflow_always_on_risk_projects_compact_summary():
    """Default-gate risk via pipeline; candidates never dropped."""
    from unittest.mock import MagicMock

    from src.application.services.pre_open_risk_inputs_builder import (
        PreOpenRiskInputsBuilder,
    )
    from src.application.services.screen_assessment_pipeline import (
        ScreenAssessmentPipeline,
    )
    from src.application.services.screen_policy import ScreenPolicy

    run_date = date(2026, 6, 18)
    candidates = [_candidate("BBCA"), _candidate("BBRI")]
    screen = FakeScreenUseCase(_screen_response(run_date, candidates=candidates))

    assessment_stub = MagicMock()
    assessment_stub.risk_level_name = "LOW_RISK"
    assessment_stub.gate_triggered = None
    assessment_stub.gate_is_structural = None
    assessment_stub.gate_confidence = 80

    risk_resp = MagicMock()
    risk_resp.assessment = assessment_stub
    risk_engine = MagicMock()
    risk_engine.assess.return_value = risk_resp

    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open(),
        risk_engine=risk_engine,
        risk_inputs_builder=PreOpenRiskInputsBuilder(),
    )
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository(
            {t: (date(2026, 1, 1), run_date) for t in ("BBCA", "BBRI")}
        ),
        broker_repository=FakeBrokerRepository(
            {t: (date(2026, 1, 1), run_date) for t in ("BBCA", "BBRI")}
        ),
        assessment_pipeline=pipeline,
        risk_engine=risk_engine,
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            regime_enabled=False,
            risk_enabled=True,
        )
    )

    assert len(response.result.candidates) == 2
    assert response.risk_by_ticker is not None
    assert set(response.risk_by_ticker) == {"BBCA", "BBRI"}
    assert response.risk_by_ticker["BBCA"] is not None
    assert response.risk_by_ticker["BBCA"].risk_level_name == "LOW_RISK"
    assert risk_engine.assess.call_count == 2


def test_pre_open_workflow_no_risk_skips_assessment():
    from unittest.mock import MagicMock

    run_date = date(2026, 6, 18)
    risk_engine = MagicMock()
    from src.application.services.pre_open_risk_inputs_builder import (
        PreOpenRiskInputsBuilder,
    )
    from src.application.services.screen_assessment_pipeline import (
        ScreenAssessmentPipeline,
    )
    from src.application.services.screen_policy import ScreenPolicy

    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open(),
        risk_engine=risk_engine,
        risk_inputs_builder=PreOpenRiskInputsBuilder(),
    )
    screen = FakeScreenUseCase(_screen_response(run_date))
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        broker_repository=FakeBrokerRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        assessment_pipeline=pipeline,
        risk_engine=risk_engine,
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            regime_enabled=False,
            risk_enabled=False,
        )
    )

    assert response.risk_by_ticker is None
    risk_engine.assess.assert_not_called()


def test_pre_open_workflow_signal_cascade_and_trade_setup_when_risk_present():
    """ADR-048: auction evidence → signal; signal+risk → TradeSetup (ADR-026)."""
    from decimal import Decimal
    from unittest.mock import MagicMock

    from src.application.services.pre_open_risk_inputs_builder import (
        PreOpenRiskInputsBuilder,
    )
    from src.application.services.screen_assessment_pipeline import (
        ScreenAssessmentPipeline,
    )
    from src.application.services.screen_policy import ScreenPolicy
    from src.domain.value_objects.screener_result import ScreenerCandidate
    from src.domain.value_objects.trade_setup import SetupAction

    run_date = date(2026, 6, 18)
    candidate = ScreenerCandidate(
        ticker="BBCA",
        iev=250_000,
        entry_price=Decimal("10050"),
        stop_loss_price=Decimal("9800"),
        capital=Decimal("3000000"),
        trend_signal="BULLISH",
        prev_close=Decimal("10000"),
        gap_pct=Decimal("1.0"),
        bid_offer_imbalance=0.65,
        spread_pct=Decimal("0.3"),
        entry_range_low=Decimal("9900"),
        entry_range_high=Decimal("10100"),
        rsi=Decimal("50"),
    )
    screen = FakeScreenUseCase(
        _screen_response(run_date, candidates=[candidate])
    )

    assessment_stub = MagicMock()
    assessment_stub.risk_level_name = "LOW_RISK"
    assessment_stub.gate_triggered = None
    assessment_stub.gate_is_structural = None
    assessment_stub.gate_confidence = 80
    risk_resp = MagicMock()
    risk_resp.assessment = assessment_stub
    risk_engine = MagicMock()
    risk_engine.assess.return_value = risk_resp

    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open(),
        risk_engine=risk_engine,
        risk_inputs_builder=PreOpenRiskInputsBuilder(),
    )
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository(
            {"BBCA": (date(2026, 1, 1), run_date)}
        ),
        broker_repository=FakeBrokerRepository(
            {"BBCA": (date(2026, 1, 1), run_date)}
        ),
        assessment_pipeline=pipeline,
        risk_engine=risk_engine,
    )

    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            regime_enabled=False,
            risk_enabled=True,
            signal_enabled=True,
        )
    )

    assert response.signal_by_ticker is not None
    assert response.signal_by_ticker["BBCA"] is not None
    assert response.signal_by_ticker["BBCA"].score >= 50
    assert response.trade_setup_by_ticker is not None
    assert response.trade_setup_by_ticker["BBCA"] is not None
    assert response.trade_setup_by_ticker["BBCA"].action in {
        SetupAction.ENTER,
        SetupAction.WATCH,
        SetupAction.AVOID,
    }
    # Annotate risk: candidate list not filtered
    assert len(response.result.candidates) == 1


def test_pre_open_workflow_signal_disabled_skips_cascade():
    run_date = date(2026, 6, 18)
    screen = FakeScreenUseCase(_screen_response(run_date))
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=screen,
        market_repository=FakeMarketRepository({"BBCA": (date(2026, 1, 1), run_date)}),
        broker_repository=FakeBrokerRepository({"BBCA": (date(2026, 1, 1), run_date)}),
    )
    response = workflow.execute(
        PreOpenWorkflowRequest(
            config=PreOpenScreenConfig(fast_mode=True),
            run_date=run_date,
            regime_enabled=False,
            risk_enabled=False,
            signal_enabled=False,
        )
    )
    assert response.signal_by_ticker is None
    assert response.trade_setup_by_ticker is None
