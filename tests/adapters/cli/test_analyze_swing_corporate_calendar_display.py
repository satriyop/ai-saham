"""Tests for print_corporate_calendar_panel (Corporate Calendar CLI panel).

Layer: Adapter (render-only). Verifies:
- no output when corporate_action_risk is None (repo/use case unavailable)
- "no configured event risk in window" line when events is empty
- full panel rendering (severity, event_type, date_role, ISO date) when
  events are present.

Capture convention: console() (src/adapters/cli/rich_display.py) builds a
plain rich.console.Console() that writes straight to stdout, so `capsys` is
sufficient — matches tests/adapters/cli/test_screen_accum_bb_diagnostic_display.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.adapters.cli.analyze_swing_corporate_calendar_display import (
    print_corporate_calendar_panel,
)
from src.adapters.cli.analyze_swing_output_context import (
    SwingOutputDisplayContext,
    SwingOutputDisplayOptions,
)
from src.application.dto.swing_analysis import (
    SwingDiagnostics,
    SwingEvidence,
    SwingVerdict,
    SignalAssessmentAvailability,
    SignalAssessmentStatus,
    SignalAssessmentUnavailableReason,
)
from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskFlag,
    CorporateActionEventRiskSeverity,
    CorporateActionRiskAssessment,
    CorporateActionRiskEvent,
)


def _evidence(corporate_action_risk=None) -> SwingEvidence:
    return SwingEvidence(
        accumulation_candidate=None,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("0.05"),
        stop_loss_pct=Decimal("0.03"),
        regime_label=None,
        corporate_action_risk=corporate_action_risk,
    )


def _options() -> SwingOutputDisplayOptions:
    return SwingOutputDisplayOptions(
        include_strategy=False,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=False,
        include_risk_detail=False,
        include_market_detail=False,
    )


def _ctx(corporate_action_risk=None) -> SwingOutputDisplayContext:
    return SwingOutputDisplayContext(
        ticker="BBCA",
        today=date(2026, 7, 13),
        strategy_name="",
        window=7,
        verdict=SwingVerdict(
            trade_setup=None,
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            signal_assessment_availability=SignalAssessmentAvailability(
                status=SignalAssessmentStatus.UNAVAILABLE,
                unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
            ),
        ),
        evidence=_evidence(corporate_action_risk),
        diagnostics=SwingDiagnostics(
            data_freshness=None,
            flow_detail=None,
            broker_detail=None,
            broker_quality_note=None,
            refresh_actions=(),
        ),
        options=_options(),
    )


def test_prints_nothing_when_corporate_action_risk_is_none(capsys):
    print_corporate_calendar_panel(_ctx(corporate_action_risk=None))

    out = capsys.readouterr().out
    assert out == ""


def test_prints_no_configured_event_risk_line_when_events_empty(capsys):
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.NONE,
        events=(),
        rationale="No configured event risk for BBCA in the queried window.",
        nearest_event_date=None,
    )

    print_corporate_calendar_panel(_ctx(corporate_action_risk=assessment))

    out = capsys.readouterr().out
    assert "Corporate Calendar: no configured event risk in window" in out


def test_prints_panel_with_event_details_for_one_event(capsys):
    event = CorporateActionRiskEvent(
        event_type="dividend",
        date_role="ex_date",
        event_date=date(2026, 7, 15),
        days_from_as_of=2,
        severity=CorporateActionEventRiskSeverity.WARNING,
        flags=(CorporateActionEventRiskFlag.PRICE_DISTORTION,),
        note=None,
        source_event_id="div-1",
    )
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.WARNING,
        events=(event,),
        rationale="dividend ex_date on 2026-07-15 (warning)",
        nearest_event_date=date(2026, 7, 15),
    )

    print_corporate_calendar_panel(_ctx(corporate_action_risk=assessment))

    out = capsys.readouterr().out
    assert "Corporate Calendar" in out
    assert "WARNING" in out
    assert "dividend" in out
    assert "ex_date" in out
    assert "2026-07-15" in out
    assert "(+2d)" in out
    assert "price_distortion" in out


def test_prints_panel_with_two_events_and_signed_day_offsets(capsys):
    event_future = CorporateActionRiskEvent(
        event_type="rups",
        date_role="rups_date",
        event_date=date(2026, 7, 17),
        days_from_as_of=4,
        severity=CorporateActionEventRiskSeverity.INFO,
        flags=(CorporateActionEventRiskFlag.GOVERNANCE_CONTEXT,),
        note=None,
        source_event_id="rups-1",
    )
    event_past = CorporateActionRiskEvent(
        event_type="dividend",
        date_role="cum_date",
        event_date=date(2026, 7, 12),
        days_from_as_of=-1,
        severity=CorporateActionEventRiskSeverity.WARNING,
        flags=(CorporateActionEventRiskFlag.LIQUIDITY_DISTORTION,),
        note=None,
        source_event_id="div-2",
    )
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.WARNING,
        events=(event_past, event_future),
        rationale="dividend cum_date on 2026-07-12 (warning); rups rups_date on 2026-07-17 (info)",
        nearest_event_date=date(2026, 7, 12),
    )

    print_corporate_calendar_panel(_ctx(corporate_action_risk=assessment))

    out = capsys.readouterr().out
    assert "(-1d)" in out
    assert "(+4d)" in out
    assert "INFO" in out
    assert "WARNING" in out
