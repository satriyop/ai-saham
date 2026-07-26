"""DQ-007 — InspectCanonicalSignalUseCase lean tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from types import SimpleNamespace

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.dto.inspect_canonical_signal import (
    InspectCanonicalSignalContract,
    InspectCanonicalSignalRequest,
    InspectCanonicalSignalStatus,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.inspect_canonical_signal_use_case import (
    InspectCanonicalSignalUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.signal_assessment import (
    ACCUMULATION_DISCOVERY_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)


def _session(day: date) -> EffectiveMarketSession:
    decision_at = datetime.combine(day, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=day,
        analysis_as_of=day,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _assessment(
    *,
    ticker: str = "BBCA",
    score: int = 72,
    coverage: float = 0.8,
    day: date = date(2026, 7, 7),
) -> AssessSignalResponse:
    assessment = SignalAssessment(
        identity=ACCUMULATION_DISCOVERY_IDENTITY,
        ticker=ticker,
        score=score,
        strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.WATCH,
        breakdown=(),
        rationale=("fixture",),
        snapshot_date=day,
        signal_authority_coverage=coverage,
    )
    return AssessSignalResponse(
        ticker=ticker,
        assessment=assessment,
        signal_authority_coverage=coverage,
        signal_score_raw=score,
    )


@dataclass
class FakeSessionResolver:
    session: EffectiveMarketSession
    calls: list = field(default_factory=list)

    def resolve(self, *, run_at: datetime) -> EffectiveMarketSession:
        self.calls.append(run_at)
        return self.session


@dataclass
class FakeRequestBuilder:
    built: list = field(default_factory=list)

    def build(self, *, tickers, window_days, as_of_date=None, market_context=None):
        request = SimpleNamespace(
            tickers=tickers,
            window_days=window_days,
            as_of_date=as_of_date,
            market_context=market_context,
        )
        self.built.append(request)
        return request


@dataclass
class FakeScreen:
    response: object | None = None
    error: Exception | None = None
    calls: list = field(default_factory=list)

    def execute(self, request, *, execution_context):
        self.calls.append((request, execution_context))
        if self.error is not None:
            raise self.error
        return self.response


def _screen_response(*, ticker: str, assessment: AssessSignalResponse, screen_result="pass"):
    candidate = SimpleNamespace(ticker=ticker, signal_assessment=assessment)
    observation = SimpleNamespace(
        candidate=candidate,
        screen_result=screen_result,
    )
    return SimpleNamespace(
        observation_candidates=[observation],
        candidates=[candidate],
    )


def test_inspect_returns_shared_path_assessment_fields():
    day = date(2026, 7, 7)
    assessment = _assessment(day=day, score=72, coverage=0.8)
    screen = FakeScreen(response=_screen_response(ticker="BBCA", assessment=assessment))
    builder = FakeRequestBuilder()
    resolver = FakeSessionResolver(session=_session(day))

    response = InspectCanonicalSignalUseCase(
        screen_use_case=screen,
        screen_request_builder=builder,
        session_resolver=resolver,
    ).execute(
        InspectCanonicalSignalRequest(ticker="bbca", as_of_date=day, window_days=7)
    )

    assert response.status is InspectCanonicalSignalStatus.OK
    assert response.contract is InspectCanonicalSignalContract.ACCUMULATION_FLOW
    assert response.assessment is assessment
    assert response.assessment.score == 72
    assert response.assessment.signal_authority_coverage == 0.8
    assert response.screen_result == "pass"
    assert response.effective_session is not None
    assert response.effective_session.analysis_as_of == day
    assert any("accumulation-flow" in note for note in response.notes)
    assert any("Read-only" in note for note in response.notes)

    payload = response.to_dict()
    assert payload["assessment"]["score"] == 72
    assert payload["assessment"]["signal_authority_coverage"] == 0.8
    assert "factors" not in payload
    assert "factors" not in payload["assessment"]
    assert "legacy_conditioned_score_note" in payload["assessment"]


def test_inspect_resolves_session_at_market_close_and_passes_pit_as_of():
    day = date(2026, 7, 7)
    assessment = _assessment(day=day)
    screen = FakeScreen(response=_screen_response(ticker="BBCA", assessment=assessment))
    builder = FakeRequestBuilder()
    resolver = FakeSessionResolver(session=_session(day))

    InspectCanonicalSignalUseCase(
        screen_use_case=screen,
        screen_request_builder=builder,
        session_resolver=resolver,
    ).execute(InspectCanonicalSignalRequest(ticker="BBCA", as_of_date=day))

    assert len(resolver.calls) == 1
    assert resolver.calls[0] == datetime.combine(day, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
    assert builder.built[0].as_of_date == day
    assert builder.built[0].tickers == ["BBCA"]
    context = screen.calls[0][1]
    assert isinstance(context, SignalEvidenceExecutionContext)
    assert context.effective_session.analysis_as_of == day


def test_inspect_maps_missing_sources_to_unavailable():
    day = date(2026, 7, 7)
    screen = FakeScreen(error=RuntimeError("no candles"))
    response = InspectCanonicalSignalUseCase(
        screen_use_case=screen,
        screen_request_builder=FakeRequestBuilder(),
        session_resolver=FakeSessionResolver(session=_session(day)),
    ).execute(InspectCanonicalSignalRequest(ticker="BBCA", as_of_date=day))

    assert response.status is InspectCanonicalSignalStatus.UNAVAILABLE
    assert response.assessment is None
    assert any("missing_local_source_data" in reason for reason in response.reasons)


def test_inspect_maps_missing_candidate_assessment_to_unavailable():
    day = date(2026, 7, 7)
    empty = SimpleNamespace(observation_candidates=[], candidates=[])
    response = InspectCanonicalSignalUseCase(
        screen_use_case=FakeScreen(response=empty),
        screen_request_builder=FakeRequestBuilder(),
        session_resolver=FakeSessionResolver(session=_session(day)),
    ).execute(InspectCanonicalSignalRequest(ticker="BBCA", as_of_date=day))

    assert response.status is InspectCanonicalSignalStatus.UNAVAILABLE
    assert "missing_local_source_data" in response.reasons


def test_missing_data_cannot_increase_authority_coverage_in_payload_identity():
    """DTO identity: lower/missing coverage must remain explicit, never inflated."""
    day = date(2026, 7, 7)
    low = _assessment(day=day, score=40, coverage=0.0)
    response = InspectCanonicalSignalUseCase(
        screen_use_case=FakeScreen(
            response=_screen_response(ticker="BBCA", assessment=low)
        ),
        screen_request_builder=FakeRequestBuilder(),
        session_resolver=FakeSessionResolver(session=_session(day)),
    ).execute(InspectCanonicalSignalRequest(ticker="BBCA", as_of_date=day))

    payload = response.to_dict()
    assert payload["assessment"]["signal_authority_coverage"] == 0.0
    assert payload["assessment"]["score"] == 40


def test_empty_ticker_is_error():
    day = date(2026, 7, 7)
    response = InspectCanonicalSignalUseCase(
        screen_use_case=FakeScreen(),
        screen_request_builder=FakeRequestBuilder(),
        session_resolver=FakeSessionResolver(session=_session(day)),
    ).execute(InspectCanonicalSignalRequest(ticker="  ", as_of_date=day))

    assert response.status is InspectCanonicalSignalStatus.ERROR
    assert "ticker_required" in response.reasons
