"""Display rendering tests for swing commands."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli.plan_swing_commands import FOREIGN_BOUNCE_SETUP_NAME
from src.adapters.cli.plan_swing_display import (
    SwingOutputDisplayContext,
    SwingOutputDisplayOptions,
    print_swing_output,
)
from src.application.dto.swing_analysis import (
    SwingDiagnostics,
    SwingEvidence,
    SwingVerdict,
    SignalAssessmentAvailability,
    SignalAssessmentStatus,
    SignalAssessmentUnavailableReason,
)
from src.application.services.swing_data_freshness import SwingDataFreshness
from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
    AccumScoreBreakdown,
)
from src.domain.value_objects.setup_evaluation import (
    SetupEvaluation,
    SetupGate,
    SetupMatch,
)
from tests.adapters.cli.swing_command_fixtures import _candidate


def test_swing_output_renders_rich_decision_overview(capsys):
    setup = SetupEvaluation(
        name=FOREIGN_BOUNCE_SETUP_NAME,
        match=SetupMatch.PARTIAL,
        gates=(
            SetupGate("score", True, "70.0", ">= 55"),
            SetupGate("trend", False, "DOWN", "SIDE"),
        ),
        failed_reasons=("trend: DOWN (required SIDE)",),
    )

    ctx = SwingOutputDisplayContext(
        ticker="BBCA",
        today=date(2026, 6, 19),
        strategy_name="foreign-accumulation",
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
        evidence=SwingEvidence(
            accumulation_candidate=_candidate(score=70.0, trend="DOWN"),
            setup_eval=setup,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
        ),
        diagnostics=SwingDiagnostics(
            data_freshness=SwingDataFreshness(
                as_of_date=date(2026, 6, 19),
                candle_start=date(2026, 1, 1),
                candle_end=date(2026, 6, 18),
                broker_start=date(2026, 1, 1),
                broker_end=date(2026, 6, 18),
                warnings=("Latest candle is stale",),
            ),
            flow_detail=None,
            broker_detail=None,
            broker_quality_note=None,
            refresh_actions=(),
        ),
        options=SwingOutputDisplayOptions(
            include_strategy=False,
            include_sentiment=False,
            include_flow_detail=False,
            include_signal_detail=False,
            include_risk_detail=False,
            include_market_detail=False,
        ),
    )
    print_swing_output(ctx)

    out = capsys.readouterr().out
    assert "Swing Analysis - BBCA" in out
    assert "Verdict" in out
    assert "Signal" in out
    assert "Risk" in out
    assert "SETUP EVIDENCE" in out
    assert "Plan" in out
    assert "Setup is partial" in out
    assert "Data" in out


def test_swing_output_renders_optional_evidence_as_separate_panels(capsys):
    strength = SimpleNamespace(value="STRONG")
    entry_quality = SimpleNamespace(value="ENTER")
    signal_assessment = SimpleNamespace(
        assessment=SimpleNamespace(
            score=82,
            strength=strength,
            entry_quality=entry_quality,
            score_label="82/100",
            signal_authority_coverage=1.0,
            rationale=("setup quality strong", "flow confirmation positive"),
            breakdown_dict={
                "setup_quality_group": 100.0,
                "flow_confirmation_group": 75.0,
                "signal_authority_coverage": 100.0,
            },
        ),
        coverage_warning=None,
        active_flags=(),
        flag_adjustment=0,
        raw_group_score=82,
        signal_authority_coverage=1.0,
    )
    risk_resp = SimpleNamespace(
        assessment=SimpleNamespace(
            risk_level_name="LOW_RISK",
            confidence=100,
            gate_triggered=None,
            indicators=SimpleNamespace(
                sma=Decimal("1000"),
                ema=Decimal("1010"),
                rsi=Decimal("55"),
            ),
            rationale_list=("trend constructive",),
        )
    )
    backtest_result = SimpleNamespace(
        trade_count=12,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 18),
        win_rate=Decimal("58.3"),
        profit_factor=Decimal("1.42"),
        max_drawdown_pct=Decimal("6.5"),
        avg_win=Decimal("500000"),
        avg_loss=Decimal("-300000"),
    )
    sentiment_resp = SimpleNamespace(
        warning=None,
        snapshot=SimpleNamespace(
            overall_sentiment=SimpleNamespace(value="POSITIVE"),
            total_count=8,
            positive_count=4,
            neutral_count=3,
            negative_count=1,
            confidence_pct=75,
        ),
    )

    ctx = SwingOutputDisplayContext(
        ticker="BBCA",
        today=date(2026, 6, 19),
        strategy_name="foreign-accumulation",
        window=7,
        verdict=SwingVerdict(
            trade_setup=None,
            signal_assessment=signal_assessment,
            risk_response=risk_resp,
            market_regime=None,
            signal_assessment_availability=SignalAssessmentAvailability(
                status=SignalAssessmentStatus.AVAILABLE
            ),
            market_context_trade_setup_preview=None,
        ),
        evidence=SwingEvidence(
            accumulation_candidate=_candidate(score=82.0, trend="SIDE"),
            setup_eval=None,
            backtest_result=backtest_result,
            sentiment_response=sentiment_resp,
            sentiment_warning=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
        ),
        diagnostics=SwingDiagnostics(
            data_freshness=SwingDataFreshness(
                as_of_date=date(2026, 6, 19),
                candle_start=date(2026, 1, 1),
                candle_end=date(2026, 6, 18),
                broker_start=date(2026, 1, 1),
                broker_end=date(2026, 6, 18),
                warnings=(),
            ),
            flow_detail=None,
            broker_detail=None,
            broker_quality_note=None,
            refresh_actions=(),
        ),
        options=SwingOutputDisplayOptions(
            include_strategy=True,
            include_sentiment=True,
            include_flow_detail=True,
            include_signal_detail=True,
            include_risk_detail=True,
            include_market_detail=False,
        ),
    )
    print_swing_output(ctx)

    out = capsys.readouterr().out
    assert "SIGNAL DETAIL" in out
    assert "Explains the Signal column in Verdict" in out
    assert "Scale: SignalEngine 0-100. Used in final TradeSetup: yes." in out
    assert "Setup Quality" in out
    assert "RISK DETAIL" in out
    assert "FLOW / BROKER DETAIL" in out
    assert "Composite Foreign Flow Score (7 broker sessions)" in out
    assert "ENTER-ZONE / FLOW POSITIVE" in out
    assert "Longer-term flow context below is diagnostic only" in out
    assert "Foreign Flow Score" in out
    assert "STRATEGY EVIDENCE" in out
    assert "2026-01-01 to 2026-06-18" in out
    assert "SENTIMENT EVIDENCE" in out
    assert "DETAILED HISTORY & SENTIMENT" not in out


def test_swing_flow_detail_calls_out_conflicted_negative_flow(capsys):
    risk_resp = SimpleNamespace(
        assessment=SimpleNamespace(
            risk_level_name="BLOCKED",
            confidence=80,
            gate_triggered="BandarGate",
            gate_confidence=80,
            indicators=SimpleNamespace(
                sma=Decimal("4756"),
                ema=Decimal("4869"),
                rsi=Decimal("42"),
            ),
            rationale_list=("Bandar distribution (Big Dist)",),
        )
    )
    signal_assessment = SimpleNamespace(
        assessment=SimpleNamespace(
            score=59,
            strength=SimpleNamespace(value="MODERATE"),
            entry_quality=SimpleNamespace(value="WATCH"),
            score_label="59/100",
            rationale=("Foreign flow: 36/100", "Bandar accumulation: 8/100"),
            signal_authority_coverage=1.0,
            breakdown_dict={
                "bandar_intensity": 8.3,
                "foreign_flow_quality": 35.7,
            },
        ),
        coverage_warning=None,
        signal_authority_coverage=1.0,
    )
    flow_detail = SimpleNamespace(
        window_sessions=30,
        through_date=date(2026, 6, 26),
        from_date=date(2026, 5, 7),
        total_net_flow=Decimal("-1130000000000"),
        available_sessions=30,
        buy_sessions=8,
        sell_sessions=22,
        consecutive_buy_sessions=0,
        avg_flow_ratio_pct=-11.08,
        latest_net_flow=Decimal("-87140000000"),
        latest_flow_ratio_pct=-28.14,
    )
    accum = _candidate(
        score=42.8,
        consecutive_streak=0,
        net_buy_days=3,
        total_days=7,
        avg_flow_ratio=-9.0,
        accum_score_breakdown=AccumScoreBreakdown(
            ticker="ASII",
            snapshot_date=date(2026, 6, 27),
            max_score=100.0,
            components=(
                ForeignFlowComponentScore("cons", 17.2, 17.2, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("streak", 0.0, 1.0, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("vwap", 1.2, 1.2, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("rsi", 9.4, 9.4, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("flow", 0.0, 1.0, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("bb", None, 8.3, ForeignFlowComponentStatus.DISABLED),
                ForeignFlowComponentScore("inst", 15.0, 15.0, ForeignFlowComponentStatus.AVAILABLE),
            ),
            vwap_discount_pct=1.0,
            rsi=50.0,
            avg_flow_ratio=-9.0,
            bci_label="STABLE",
        ),
        bandar_detector=SimpleNamespace(
            label="Dist | today=Big Dist",
            accumulation_score=-6,
            is_accumulating=False,
            is_distributing=True,
        ),
    )

    ctx = SwingOutputDisplayContext(
        ticker="ASII",
        today=date(2026, 6, 27),
        strategy_name=None,
        window=7,
        verdict=SwingVerdict(
            trade_setup=None,
            signal_assessment=signal_assessment,
            risk_response=risk_resp,
            market_regime=None,
            signal_assessment_availability=SignalAssessmentAvailability(
                status=SignalAssessmentStatus.AVAILABLE
            ),
            market_context_trade_setup_preview=None,
        ),
        evidence=SwingEvidence(
            accumulation_candidate=accum,
            setup_eval=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
        ),
        diagnostics=SwingDiagnostics(
            data_freshness=SwingDataFreshness(
                as_of_date=date(2026, 6, 27),
                candle_start=date(2026, 1, 1),
                candle_end=date(2026, 6, 26),
                broker_start=date(2026, 1, 1),
                broker_end=date(2026, 6, 26),
                warnings=(),
            ),
            flow_detail=flow_detail,
            broker_detail=None,
            broker_quality_note=None,
            refresh_actions=(),
        ),
        options=SwingOutputDisplayOptions(
            include_strategy=False,
            include_sentiment=False,
            include_flow_detail=True,
            include_signal_detail=True,
            include_risk_detail=False,
            include_market_detail=False,
        ),
    )
    print_swing_output(ctx)

    import re

    out = capsys.readouterr().out
    # Strip ANSI/box glyphs and collapse wrap so Rich layout cannot break
    # multi-word substring asserts.
    plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out)
    plain = re.sub(r"[─│╭╮╰╯├┤┬┴┼┌┐└┘━┃┏┓┗┛]", " ", plain)
    flat = " ".join(plain.split())
    assert "WATCH-ZONE / FLOW NEGATIVE" in flat
    assert "current foreign flow is not confirming" in flat
    assert "Bandar detector shows distribution" in flat
    assert "Flow ratio" in flat
    assert "0.0" in flat
    assert "lacks foreign-flow" in flat
    assert "confirmation" in flat
    assert "recent signal-window accumulation is occurring" not in flat


def test_cli_rendering_of_unavailable_reasons():
    from rich.console import Console
    from src.adapters.cli.plan_swing_overview_panels import _signal_label, _build_signal_panel

    reasons_map = [
        (SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE, "no production signal evidence"),
        (SignalAssessmentUnavailableReason.SIGNAL_ENGINE_UNAVAILABLE, "signal engine unavailable"),
        (SignalAssessmentUnavailableReason.ASSESSMENT_FAILED, "assessment failed"),
    ]

    for reason, expected_text in reasons_map:
        availability = SignalAssessmentAvailability(
            status=SignalAssessmentStatus.UNAVAILABLE,
            unavailable_reason=reason,
        )

        # Test _signal_label
        label_text, style, detail = _signal_label(None, availability)
        assert label_text == "N/A"
        assert style == "bright_black"
        assert expected_text in detail

        # Test _build_signal_panel
        panel_obj = _build_signal_panel(None, availability)
        console = Console(color_system=None)
        with console.capture() as capture:
            console.print(panel_obj)
        rendered = capture.get().lower()
        assert expected_text in rendered


def test_cli_rendering_missing_availability_raises_type_error():
    from src.adapters.cli.plan_swing_overview_panels import _signal_label, _build_signal_panel
    import pytest

    with pytest.raises(TypeError):
        _signal_label(None, None)

    with pytest.raises(TypeError):
        _build_signal_panel(None, None)
