"""Tests for post-open intraday confirmation use case."""

from datetime import date
from decimal import Decimal

from src.application.use_case.pre_open_post_open_gates_use_case import (
    PreOpenPostOpenGatesRequest,
    PreOpenPostOpenGatesUseCase,
)
from src.domain.value_objects.pre_open_post_open_assessment import (
    PreOpenPostOpenCandidate,
    PreOpenPostOpenDecision,
)


def _candidate(**overrides) -> PreOpenPostOpenCandidate:
    data = {
        "ticker": "BBCA",
        "opening_price": Decimal("9050"),
        "iev": 450000,
        "entry_range_low": Decimal("8800"),
        "entry_range_high": Decimal("9300"),
        "suggested_entry": Decimal("9050"),
        "atr_stop": Decimal("8900"),
        "trend": "BULLISH",
        "rsi": Decimal("52"),
    }
    data.update(overrides)
    return PreOpenPostOpenCandidate(**data)


def _confirm(candidate: PreOpenPostOpenCandidate):
    use_case = PreOpenPostOpenGatesUseCase()
    result = use_case.execute(
        PreOpenPostOpenGatesRequest(
            candidates=[candidate],
            run_date=date(2026, 6, 12),
            max_stop_pct=Decimal("0.07"),
        )
    )
    return result.confirmations[0]


def test_enter_when_open_inside_range_bullish_and_risk_valid():
    confirmation = _confirm(_candidate())

    assert confirmation.decision == PreOpenPostOpenDecision.ENTER
    assert confirmation.planned_entry == Decimal("9050")
    assert confirmation.stop_pct == Decimal("1.7")
    assert "open inside entry range" in confirmation.reasons


def test_wait_when_open_inside_range_but_not_bullish():
    confirmation = _confirm(_candidate(trend="NEUTRAL"))

    assert confirmation.decision == PreOpenPostOpenDecision.WAIT
    assert "pre-open trend is not bullish" in confirmation.reasons


def test_skip_gap_up_when_open_above_range():
    confirmation = _confirm(_candidate(opening_price=Decimal("9400")))

    assert confirmation.decision == PreOpenPostOpenDecision.SKIP_GAP_UP
    assert "above range high" in confirmation.reasons[0]


def test_skip_gap_down_when_open_below_range():
    confirmation = _confirm(_candidate(opening_price=Decimal("8700")))

    assert confirmation.decision == PreOpenPostOpenDecision.SKIP_GAP_DOWN
    assert "below range low" in confirmation.reasons[0]


def test_skip_bearish_context_when_preopen_trend_bearish():
    confirmation = _confirm(_candidate(trend="BEARISH"))

    assert confirmation.decision == PreOpenPostOpenDecision.SKIP_BEARISH_CONTEXT
    assert "pre-open trend is BEARISH" in confirmation.reasons


def test_skip_bearish_context_when_accumulation_distributing():
    confirmation = _confirm(_candidate(opening_broker_backing_tag="DISTRIBUTING"))

    assert confirmation.decision == PreOpenPostOpenDecision.SKIP_BEARISH_CONTEXT
    assert "broker context is DISTRIBUTING" in confirmation.reasons


def test_skip_risk_too_wide_when_stop_exceeds_max():
    confirmation = _confirm(_candidate(atr_stop=Decimal("8300")))

    assert confirmation.decision == PreOpenPostOpenDecision.SKIP_RISK_TOO_WIDE
    assert confirmation.stop_pct == Decimal("8.3")


def test_skip_insufficient_data_when_open_missing():
    confirmation = _confirm(_candidate(opening_price=None))

    assert confirmation.decision == PreOpenPostOpenDecision.SKIP_INSUFFICIENT_DATA
    assert confirmation.reasons == ("missing opening price",)
