"""Tests for the risk analysis workflow use case."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.dto.assess_risk import AssessRiskResponse
from src.application.use_case.run_risk_analysis_workflow_use_case import (
    RunRiskAnalysisWorkflowRequest,
    RunRiskAnalysisWorkflowUseCase,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment


class FakeRiskEngine:
    def __init__(self, response: AssessRiskResponse, trend_response=None, trend_error=None):
        self.response = response
        self.trend_response = trend_response
        self.trend_error = trend_error
        self.assess_requests = []
        self.trend_requests = []

    def assess_request(self, request):
        self.assess_requests.append(request)
        return self.response

    def assess_trend(self, request, days):
        self.trend_requests.append((request, days))
        if self.trend_error is not None:
            raise self.trend_error
        return self.trend_response


class FakeSentimentFetcher:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot
        self.error = error
        self.calls = []

    def __call__(self, ticker, provider_name, no_ai):
        self.calls.append((ticker, provider_name, no_ai))
        if self.error is not None:
            raise self.error
        return self.snapshot


def _response(gate_triggered: str | None = None) -> AssessRiskResponse:
    assessment = RiskAssessment(
        rationale=("reason one",),
        snapshot_date=date(2026, 7, 10),
        indicators=IndicatorSnapshot(
            date=date(2026, 7, 10),
            sma=Decimal("1000"),
            ema=Decimal("1010"),
            rsi=Decimal("55.5"),
        ),
        gate_triggered=gate_triggered,
        gate_confidence=80 if gate_triggered else None,
    )
    return AssessRiskResponse(
        ticker="BBCA",
        assessment=assessment,
        sma_period=20,
        ema_period=20,
        rsi_period=14,
    )


def _request(**overrides) -> RunRiskAnalysisWorkflowRequest:
    defaults = dict(
        ticker="BBCA",
        sma_period=20,
        ema_period=20,
        rsi_period=14,
        rules_file=None,
        include_sentiment=False,
        sentiment_provider_name="composite",
        no_ai_sentiment=False,
        trend_days=0,
    )
    defaults.update(overrides)
    return RunRiskAnalysisWorkflowRequest(**defaults)


def test_executes_risk_assessment_and_returns_structured_result():
    response = _response()
    engine = FakeRiskEngine(response=response)
    use_case = RunRiskAnalysisWorkflowUseCase(risk_engine=engine)

    result = use_case.execute(_request())

    assert result.ticker == "BBCA"
    assert result.response is response
    assert result.sentiment_snapshot is None
    assert result.trend_response is None
    assert result.warnings == ()
    assert len(engine.assess_requests) == 1


def test_json_dict_matches_schema_keys_exactly():
    response = _response(gate_triggered="LiquidityGate")
    engine = FakeRiskEngine(response=response)
    use_case = RunRiskAnalysisWorkflowUseCase(risk_engine=engine)

    result = use_case.execute(_request())
    payload = result.to_json_dict()

    assert payload == {
        "schema_version": 1,
        "artifact_type": "risk_assessment",
        "ticker": "BBCA",
        "risk_status": "BLOCKED",
        "status": "BLOCKED",
        "verdict": "BLOCKED",
        "gate_triggered": "LiquidityGate",
        "gate_confidence": 80,
        "rationale": ["reason one"],
        "indicators": {
            "sma_20": 1000.0,
            "ema_20": 1010.0,
            "rsi_14": 55.5,
        },
    }


def test_sentiment_fetch_failure_becomes_warning_and_does_not_fail():
    response = _response()
    engine = FakeRiskEngine(response=response)
    fetcher = FakeSentimentFetcher(error=RuntimeError("network down"))
    use_case = RunRiskAnalysisWorkflowUseCase(risk_engine=engine, sentiment_fetcher=fetcher)

    result = use_case.execute(_request(include_sentiment=True))

    assert result.sentiment_snapshot is None
    assert len(result.warnings) == 1
    assert "Could not fetch sentiment: network down" in result.warnings[0]
    # Assessment still executed with no sentiment attached.
    assert engine.assess_requests[0].sentiment is None


def test_trend_is_skipped_when_rules_file_is_provided():
    response = _response()
    engine = FakeRiskEngine(response=response)
    use_case = RunRiskAnalysisWorkflowUseCase(risk_engine=engine)

    result = use_case.execute(_request(rules_file=Path("config/my_rules.yaml"), trend_days=7))

    assert result.trend_response is None
    assert engine.trend_requests == []


def test_trend_failure_becomes_warning_and_does_not_fail():
    response = _response()
    engine = FakeRiskEngine(response=response, trend_error=ValueError("insufficient data"))
    use_case = RunRiskAnalysisWorkflowUseCase(risk_engine=engine)

    result = use_case.execute(_request(trend_days=5))

    assert result.trend_response is None
    assert any("Trend unavailable: insufficient data" in w for w in result.warnings)


def test_sentiment_snapshot_is_included_when_sentiment_fetch_succeeds():
    response = _response()
    engine = FakeRiskEngine(response=response)
    fetcher = FakeSentimentFetcher(snapshot="fake-snapshot")
    use_case = RunRiskAnalysisWorkflowUseCase(risk_engine=engine, sentiment_fetcher=fetcher)

    result = use_case.execute(
        _request(include_sentiment=True, sentiment_provider_name="google", no_ai_sentiment=True)
    )

    assert result.sentiment_snapshot == "fake-snapshot"
    assert result.warnings == ()
    assert fetcher.calls == [("BBCA", "google", True)]
    assert engine.assess_requests[0].sentiment == "fake-snapshot"
