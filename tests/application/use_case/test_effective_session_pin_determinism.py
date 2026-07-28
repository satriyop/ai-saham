"""Pinned as-of determinism for accumulation screen scoring.

Cross-command equality (screen accum vs plan swing) is not duplicated here
with a full swing workflow harness: both paths share the same pinned
``as_of_date``, ``MARKET_CLOSE`` WIB ``run_at``, and
``SignalEvidenceExecutionContext`` when ``--as-of`` is set. This module proves
determinism and identical session/score fields on the shared screen use case
that swing's candidate builder delegates to.
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    _candle,
    _summary,
    _weekdays,
    make_signal_evidence_execution_context,
)


def _screen_request(as_of: date) -> AccumulationScreenRequest:
    return AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=0,
        min_accum_score=0.0,
        min_accum_score_enabled=True,
        as_of_date=as_of,
    )


def _build_use_case(session_dates):
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    return AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )


def _metrics(candidate):
    breakdown = candidate.signal_assessment.assessment.breakdown_dict
    return candidate.accum_score, breakdown["flow_confirmation_group"]


def test_pinned_as_of_screen_runs_are_deterministic():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    pinned = session_dates[-1]
    use_case = _build_use_case(session_dates)
    context = make_signal_evidence_execution_context(pinned)
    request = _screen_request(pinned)

    first = use_case.execute(request, execution_context=context)
    second = use_case.execute(request, execution_context=context)

    c1 = first.candidates[0]
    c2 = second.candidates[0]
    assert c1.signal_assessment is not None
    assert c2.signal_assessment is not None
    assert _metrics(c1) == _metrics(c2)


def test_pinned_as_of_session_fields_match_market_close_pin():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    pinned = session_dates[-1]
    use_case = _build_use_case(session_dates)
    context = make_signal_evidence_execution_context(pinned)

    response = use_case.execute(_screen_request(pinned), execution_context=context)
    session = context.effective_session

    assert session.analysis_as_of == pinned
    assert session.is_eod_pending is False
    assert response.candidates[0].accum_score is not None


def test_swing_style_candidate_lookup_matches_direct_screen_for_same_pin():
    """Swing's candidate builder calls the same screen use case with pinned today."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    pinned = session_dates[-1]
    use_case = _build_use_case(session_dates)
    context = make_signal_evidence_execution_context(pinned)
    request = _screen_request(pinned)

    screen_response = use_case.execute(request, execution_context=context)
    swing_style_response = use_case.execute(request, execution_context=context)

    screen_candidate = screen_response.candidates[0]
    swing_candidate = swing_style_response.candidates[0]
    assert _metrics(screen_candidate) == _metrics(swing_candidate)
