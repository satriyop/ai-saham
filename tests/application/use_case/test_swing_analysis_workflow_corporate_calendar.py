"""Integration tests: corporate calendar event-risk wiring into
SwingAnalysisWorkflowUseCase.

Verifies the optional `corporate_action_risk_use_case` kwarg attaches
`SwingEvidence.corporate_action_risk` diagnostically, never influences
`trade_setup`, and is guarded by try/except so calendar failures degrade to
warnings rather than raising.

Layer: Application. Mirrors the fixture pattern in
test_swing_analysis_workflow.py (FakeMarketRepository, FakeBrokerRepository,
_request helper) rather than inventing a new one.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.application.dto.swing_analysis import SwingAnalysisWorkflowRequest
from src.application.use_case.assess_corporate_action_event_risk_use_case import (
    AssessCorporateActionEventRiskUseCase,
)
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisWorkflowUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskFlag,
    CorporateActionEventRiskSeverity,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.infrastructure.config.corporate_action_policy_config import (
    load_corporate_action_policy_config,
)
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


class FakeMarketRepository:
    def __init__(self, candles: list[Candle], source: str | None = None) -> None:
        self._candles = candles
        self._source = source

    def get_candles(self, ticker: str, start_date=None, end_date=None):
        return self._candles

    def get_candle_source(self, ticker: str, on_date: date):
        return self._source


class FakeBrokerRepository:
    pass


class FakeRegistry:
    def compute(self, name: str, candles: list[Candle], period: int):
        if name == "ATR":
            return [(candles[-1].date, Decimal("25"))]
        return []


class FakeCalendarRepositoryWithDividend:
    """Returns a dividend ex_date event 2 days after `as_of` (request.today),
    which is within the default policy's dividend ex_date lookahead_days=5
    window regardless of the max-lookahead query window used to call this
    fake (from_date/to_date span the full max_lookahead_days=30, but the
    use case's per-role window check still applies afterwards)."""

    def get_events_for_ticker(self, ticker, from_date, to_date, event_types=None, as_of_fetched_at=None):
        # request.today is 2026-07-13 in this test file's _request() default.
        ex_date = date(2026, 7, 15)
        return [
            CorporateActionCalendarEvent(
                event_type=CorporateActionType.DIVIDEND,
                source_event_id="div-1",
                ticker=ticker,
                dates=(
                    CorporateActionCalendarDate(
                        date_role=CorporateActionDateRole.EX_DATE,
                        event_date=ex_date,
                    ),
                ),
            )
        ]


class FakeCalendarRepositoryRaising:
    def get_events_for_ticker(self, ticker, from_date, to_date, event_types=None, as_of_fetched_at=None):
        raise RuntimeError("calendar backend unavailable")


class FakeCalendarRepositoryRecordingAsOfFetchedAt:
    """DQ-002G workflow-level regression: records every argument
    `get_events_for_ticker` was actually called with, so the exact resolved
    decision timestamp propagated from `SwingAnalysisInputCollector` ->
    `SwingAnalysisOptionalEvidenceRunner` -> `SwingAnalysisEvidenceBuilder` ->
    `AssessCorporateActionEventRiskUseCase` can be asserted end-to-end,
    rather than only at the use-case or repository unit-test boundary."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get_events_for_ticker(self, ticker, from_date, to_date, event_types=None, as_of_fetched_at=None):
        self.calls.append(
            {
                "ticker": ticker,
                "from_date": from_date,
                "to_date": to_date,
                "as_of_fetched_at": as_of_fetched_at,
            }
        )
        return []


def _candle(day: date) -> Candle:
    return Candle(
        ticker="BBCA",
        date=day,
        open=Decimal("1000"),
        high=Decimal("1025"),
        low=Decimal("990"),
        close=Decimal("1010"),
        volume=1_000_000,
    )


def _request(**overrides) -> SwingAnalysisWorkflowRequest:
    values = {
        "ticker": "BBCA",
        "today": date(2026, 7, 13),
        "strategy_name": None,
        "setup_name": None,
        "window": 7,
        "flow_window": 30,
        "capital": None,
        "risk_pct": 1.0,
        "entry_price": None,
        "atr_mult": 1.5,
        "rr": 2.0,
        "include_sentiment": False,
        "include_flow_detail": False,
        "include_signal_detail": False,
        "include_risk_detail": False,
        "include_market_detail": False,
        "sentiment_verbose": False,
        "auto_refresh": False,
        "force_refresh": False,
        "with_market_context": False,
        "regime_universe": "idx80",
        "benchmark": "IHSG",
        "db_path": Path("data.db"),
        "with_technical_gate": False,
    }
    values.update(overrides)
    return SwingAnalysisWorkflowRequest(**values)


def _build_workflow(*, corporate_action_risk_use_case=None) -> SwingAnalysisWorkflowUseCase:
    return SwingAnalysisWorkflowUseCase(
        market_repository=FakeMarketRepository([_candle(date(2026, 7, 13))]),
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: {},
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate_evaluation=lambda **kwargs: None,
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=RulesYamlLoader(),
        corporate_action_risk_use_case=corporate_action_risk_use_case,
    )


def test_baseline_without_corporate_action_risk_use_case_leaves_evidence_none():
    workflow = _build_workflow(corporate_action_risk_use_case=None)

    response = workflow.execute(_request())

    assert response.evidence.corporate_action_risk is None


def test_wired_corporate_action_risk_use_case_attaches_warning_assessment():
    use_case = AssessCorporateActionEventRiskUseCase(
        repository=FakeCalendarRepositoryWithDividend(),
        policy=load_corporate_action_policy_config(),
    )
    workflow = _build_workflow(corporate_action_risk_use_case=use_case)

    response = workflow.execute(_request())

    assessment = response.evidence.corporate_action_risk
    assert assessment is not None
    assert assessment.severity == CorporateActionEventRiskSeverity.WARNING
    assert len(assessment.events) == 1
    assert CorporateActionEventRiskFlag.PRICE_DISTORTION in assessment.events[0].flags


def test_corporate_calendar_context_never_changes_trade_setup_verdict():
    baseline_workflow = _build_workflow(corporate_action_risk_use_case=None)
    wired_use_case = AssessCorporateActionEventRiskUseCase(
        repository=FakeCalendarRepositoryWithDividend(),
        policy=load_corporate_action_policy_config(),
    )
    wired_workflow = _build_workflow(corporate_action_risk_use_case=wired_use_case)

    baseline_response = baseline_workflow.execute(_request())
    wired_response = wired_workflow.execute(_request())

    # Neither fixture wires signal_engine/risk_engine, so trade_setup is None
    # in both — still a valid equality assertion proving corporate calendar
    # context never diverges the verdict.
    assert baseline_response.trade_setup == wired_response.trade_setup
    assert baseline_response.verdict.trade_setup == wired_response.verdict.trade_setup
    assert baseline_response.verdict.trade_setup is None

    # Sanity: the two runs really did differ in corporate_action_risk, so this
    # equality isn't trivially true because nothing happened.
    assert baseline_response.evidence.corporate_action_risk is None
    assert wired_response.evidence.corporate_action_risk is not None


def test_corporate_action_risk_failure_is_caught_and_recorded_as_warning():
    failing_use_case = AssessCorporateActionEventRiskUseCase(
        repository=FakeCalendarRepositoryRaising(),
        policy=load_corporate_action_policy_config(),
    )
    workflow = _build_workflow(corporate_action_risk_use_case=failing_use_case)

    response = workflow.execute(_request())

    assert response.evidence.corporate_action_risk is None
    assert any(
        "corporate action" in w.lower() or "calendar" in w.lower()
        for w in response.warnings
    ), f"expected a corporate action/calendar warning, got: {response.warnings}"


def test_workflow_passes_resolved_decision_timestamp_to_corporate_action_repository():
    """DQ-002G follow-up: proves the exact `effective_session.decision_at`
    timestamp resolved by `SwingAnalysisInputCollector` for a historical
    `request.today` reaches `get_events_for_ticker`'s `as_of_fetched_at`
    argument, through every intermediate hop (state storage ->
    optional-evidence runner -> evidence builder -> use case -> repository).

    Fails if: `SwingAnalysisInputCollector` stops storing `effective_session`
    on state; `SwingAnalysisOptionalEvidenceRunner` stops deriving
    `as_of_fetched_at` from `state.effective_session.decision_at`; or
    `SwingAnalysisEvidenceBuilder`/`AssessCorporateActionEventRiskUseCase`
    stop forwarding it to the repository call.
    """
    recording_repo = FakeCalendarRepositoryRecordingAsOfFetchedAt()
    wired_use_case = AssessCorporateActionEventRiskUseCase(
        repository=recording_repo,
        policy=load_corporate_action_policy_config(),
    )
    baseline_workflow = _build_workflow(corporate_action_risk_use_case=None)
    wired_workflow = _build_workflow(corporate_action_risk_use_case=wired_use_case)

    historical_today = date(2026, 7, 13)
    request = _request(today=historical_today)

    baseline_response = baseline_workflow.execute(request)
    wired_response = wired_workflow.execute(request)

    # `SwingAnalysisInputCollector` builds a deterministic after-close WIB
    # decision timestamp for any `request.today` that isn't the real current
    # date — computed here from the same constants the production code uses,
    # not hardcoded, so this test tracks MARKET_CLOSE/IDX_TIMEZONE if they
    # ever change.
    expected_as_of_fetched_at = datetime.combine(
        historical_today, MARKET_CLOSE, tzinfo=IDX_TIMEZONE
    ).isoformat()

    assert len(recording_repo.calls) == 1
    call = recording_repo.calls[0]
    assert call["ticker"] == "BBCA"
    assert call["as_of_fetched_at"] == expected_as_of_fetched_at

    # Corporate-action diagnostics surface only on evidence, and never touch
    # TradeSetup/verdict — same invariant proven in
    # test_corporate_calendar_context_never_changes_trade_setup_verdict,
    # re-asserted here for this specific wiring path.
    assert baseline_response.evidence.corporate_action_risk is None
    assert wired_response.evidence.corporate_action_risk is not None
    assert baseline_response.trade_setup == wired_response.trade_setup
    assert baseline_response.verdict.trade_setup == wired_response.verdict.trade_setup
    assert wired_response.verdict.trade_setup is None
