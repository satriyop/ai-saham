"""RC-04 screen judgment authority and missing-state contract."""

from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace

import pytest

from src.application.dto.plan_swing import (
    ScreenJudgmentStatus,
    ScreenJudgmentUnavailableReason,
)
from src.application.services import swing_judgment_authority
from src.application.services.swing_judgment_authority import (
    ScreenJudgmentInvariantError,
    resolve_screen_judgment,
)
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup

SNAP = date(2026, 8, 7)


def _setup(*, ticker: str = "BBCA", snapshot_date: date = SNAP) -> TradeSetup:
    return TradeSetup(
        ticker=ticker,
        snapshot_date=snapshot_date,
        action=SetupAction.WATCH,
        signal_score=70,
        signal_score_raw=70,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="screen",
    )


def _evaluation(*, signal=object(), risk=object(), setup=None, ticker: str = "BBCA", day=SNAP):
    return SimpleNamespace(
        analysis_date=day,
        candidate=SimpleNamespace(
            ticker=ticker,
            signal_assessment=signal,
            risk_assessment=risk,
            trade_setup=setup,
        ),
    )


@pytest.mark.parametrize(
    ("evaluation", "reason"),
    [
        (None, ScreenJudgmentUnavailableReason.NO_SCREEN_CANDIDATE),
        (
            _evaluation(signal=None, risk=None),
            ScreenJudgmentUnavailableReason.NO_SCREEN_SIGNAL_ASSESSMENT,
        ),
        (
            _evaluation(risk=None),
            ScreenJudgmentUnavailableReason.NO_SCREEN_RISK_ASSESSMENT,
        ),
        (_evaluation(), ScreenJudgmentUnavailableReason.NO_SCREEN_TRADE_SETUP),
    ],
)
def test_missing_screen_judgment_has_closed_reason_precedence(evaluation, reason) -> None:
    result = resolve_screen_judgment(
        evaluation,
        expected_ticker="bbca",
        expected_snapshot_date=SNAP,
    )
    assert result.status is ScreenJudgmentStatus.UNAVAILABLE
    assert result.trade_setup is None
    assert result.unavailable_reason is reason


def test_available_preserves_exact_screen_trade_setup() -> None:
    setup = _setup()
    result = resolve_screen_judgment(
        _evaluation(setup=setup),
        expected_ticker="BBCA",
        expected_snapshot_date=SNAP,
    )
    assert result.status is ScreenJudgmentStatus.AVAILABLE
    assert result.trade_setup is setup
    assert result.unavailable_reason is None


@pytest.mark.parametrize(
    "evaluation",
    [
        _evaluation(ticker="BBRI"),
        _evaluation(day=date(2026, 8, 6)),
        _evaluation(setup=_setup(ticker="BBRI")),
        _evaluation(setup=_setup(snapshot_date=date(2026, 8, 6))),
        _evaluation(signal=None, setup=_setup()),
        _evaluation(risk=None, setup=_setup()),
    ],
)
def test_conflicting_present_screen_authority_fails_closed(evaluation) -> None:
    with pytest.raises(ScreenJudgmentInvariantError):
        resolve_screen_judgment(
            evaluation,
            expected_ticker="BBCA",
            expected_snapshot_date=SNAP,
        )


def test_resolver_has_no_fallback_or_recompute_input() -> None:
    assert set(inspect.signature(resolve_screen_judgment).parameters) == {
        "evaluation",
        "expected_ticker",
        "expected_snapshot_date",
    }
    assert not hasattr(swing_judgment_authority, "resolve_authoritative_trade_setup")
    assert not hasattr(swing_judgment_authority, "allow_action_recompute")
