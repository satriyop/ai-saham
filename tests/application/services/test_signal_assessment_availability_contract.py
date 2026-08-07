"""Typed screen judgment reference and plan JSON contract tests."""

from datetime import date
from types import SimpleNamespace

import pytest

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.dto.plan_swing import (
    ScreenJudgmentReference,
    ScreenJudgmentSource,
    ScreenJudgmentStatus,
    ScreenJudgmentUnavailableReason,
    SwingVerdict,
)
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup


def test_unavailable_requires_reason_and_no_trade_setup() -> None:
    with pytest.raises(ValueError, match="requires a reason"):
        ScreenJudgmentReference(
            status=ScreenJudgmentStatus.UNAVAILABLE,
            source=ScreenJudgmentSource.SCREEN_ACCUM,
            ticker="BBCA",
            snapshot_date=date(2026, 6, 18),
            trade_setup=None,
        )


def test_available_requires_trade_setup() -> None:
    with pytest.raises(ValueError, match="requires the screen trade_setup"):
        ScreenJudgmentReference(
            status=ScreenJudgmentStatus.AVAILABLE,
            source=ScreenJudgmentSource.SCREEN_ACCUM,
            ticker="BBCA",
            snapshot_date=date(2026, 6, 18),
            trade_setup=None,
        )


def test_status_and_reason_must_be_typed() -> None:
    with pytest.raises(TypeError, match="ScreenJudgmentStatus"):
        ScreenJudgmentReference(
            status="UNAVAILABLE",
            source=ScreenJudgmentSource.SCREEN_ACCUM,
            ticker="BBCA",
            snapshot_date=date(2026, 6, 18),
            trade_setup=None,
            unavailable_reason=ScreenJudgmentUnavailableReason.NO_SCREEN_CANDIDATE,
        )
    with pytest.raises(TypeError, match="ScreenJudgmentUnavailableReason"):
        ScreenJudgmentReference(
            status=ScreenJudgmentStatus.UNAVAILABLE,
            source=ScreenJudgmentSource.SCREEN_ACCUM,
            ticker="BBCA",
            snapshot_date=date(2026, 6, 18),
            trade_setup=None,
            unavailable_reason="no_screen_candidate",
        )


def test_reference_rejects_noncanonical_ticker() -> None:
    with pytest.raises(ValueError, match="canonical uppercase"):
        ScreenJudgmentReference(
            status=ScreenJudgmentStatus.UNAVAILABLE,
            source=ScreenJudgmentSource.SCREEN_ACCUM,
            ticker="bbca",
            snapshot_date=date(2026, 6, 18),
            trade_setup=None,
            unavailable_reason=ScreenJudgmentUnavailableReason.NO_SCREEN_CANDIDATE,
        )


@pytest.mark.parametrize("reason", tuple(ScreenJudgmentUnavailableReason))
def test_unavailable_verdict_json_has_no_action_or_removed_plan_fields(reason) -> None:
    ref = ScreenJudgmentReference(
        status=ScreenJudgmentStatus.UNAVAILABLE,
        source=ScreenJudgmentSource.SCREEN_ACCUM,
        ticker="BBCA",
        snapshot_date=date(2026, 8, 7),
        trade_setup=None,
        unavailable_reason=reason,
    )
    payload = SwingVerdict(
        judgment_ref=ref,
        signal_assessment=None,
        risk_assessment=None,
    ).to_dict()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["source"] == "screen_accum"
    assert payload["action"] is None
    assert payload["trade_setup"] is None
    assert payload["unavailable_reason"] == reason.value
    assert "risk_response" not in payload
    assert "market_regime" not in payload
    assert "market_context_trade_setup_preview" not in payload


def test_available_verdict_json_preserves_screen_action_and_components() -> None:
    snapshot = date(2026, 8, 7)
    setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=snapshot,
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
    signal = AssessSignalResponse(
        ticker="BBCA",
        assessment=SignalAssessment(
            identity=SWING_TRADE_SETUP_IDENTITY,
            ticker="BBCA",
            snapshot_date=snapshot,
            score=70,
            strength=SignalStrength.STRONG,
            entry_quality=EntryQuality.WATCH,
            breakdown=(),
            rationale=(),
            signal_authority_coverage=None,
        ),
    )
    risk = SimpleNamespace(to_dict=lambda: {"gate_triggered": None})
    payload = SwingVerdict(
        judgment_ref=ScreenJudgmentReference(
            status=ScreenJudgmentStatus.AVAILABLE,
            source=ScreenJudgmentSource.SCREEN_ACCUM,
            ticker="BBCA",
            snapshot_date=snapshot,
            trade_setup=setup,
        ),
        signal_assessment=signal,
        risk_assessment=risk,
    ).to_dict()
    assert payload["status"] == "AVAILABLE"
    assert payload["action"] == "WATCH"
    assert payload["trade_setup"] == setup.to_dict()
    assert payload["signal_assessment"]["score"] == 70
    assert payload["risk_assessment"] == {"gate_triggered": None}
