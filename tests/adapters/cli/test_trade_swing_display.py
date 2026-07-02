from datetime import date
from decimal import Decimal

from src.adapters.cli.trade_swing_display import display_swing_backtest
from src.application.services.swing_backtest_attribution import (
    AttributionGroupStat,
    CandidateAttributionStat,
    SampleQuality,
    SwingBacktestAttributionSummary,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse


def _response() -> SwingBacktestResponse:
    return SwingBacktestResponse(
        setup="foreign-bounce",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        initial_capital=Decimal("1000000"),
        cost_bps=Decimal("20"),
        final_equity=Decimal("1010000"),
        total_return_pct=1.0,
        max_drawdown_pct=-1.0,
        trade_count=2,
        win_rate_pct=50.0,
        avg_trade_return_pct=1.0,
        profit_factor=1.5,
        exposure_pct=25.0,
        skipped_no_cash=0,
        skipped_duplicate=0,
        skipped_no_forward_data=0,
        skipped_by_regime=0,
        attribution_summary=SwingBacktestAttributionSummary(
            group_stats=(
                AttributionGroupStat(
                    dimension="signal_strength",
                    bucket="STRONG",
                    trade_count=2,
                    win_rate_pct=50.0,
                    avg_return_pct=1.0,
                    total_pnl=Decimal("10000"),
                    profit_factor=1.5,
                ),
                AttributionGroupStat(
                    dimension="signal_score_bucket",
                    bucket="HIGH_70_PLUS",
                    trade_count=2,
                    win_rate_pct=50.0,
                    avg_return_pct=1.0,
                    total_pnl=Decimal("10000"),
                    profit_factor=1.5,
                ),
            ),
            candidate_group_stats=(
                CandidateAttributionStat(
                    dimension="candidate_setup_match",
                    bucket="NO_MATCH",
                    observation_count=1,
                    win_rate_pct=100.0,
                    avg_forward_return_pct=4.0,
                ),
            ),
        ),
    )


def _candidate_only_response() -> SwingBacktestResponse:
    response = _response()
    return SwingBacktestResponse(
        setup=response.setup,
        start_date=response.start_date,
        end_date=response.end_date,
        initial_capital=response.initial_capital,
        cost_bps=response.cost_bps,
        final_equity=response.final_equity,
        total_return_pct=response.total_return_pct,
        max_drawdown_pct=response.max_drawdown_pct,
        trade_count=0,
        win_rate_pct=None,
        avg_trade_return_pct=None,
        profit_factor=None,
        exposure_pct=response.exposure_pct,
        skipped_no_cash=0,
        skipped_duplicate=0,
        skipped_no_forward_data=0,
        skipped_by_regime=0,
        attribution_summary=SwingBacktestAttributionSummary(
            candidate_group_stats=response.attribution_summary.candidate_group_stats,
        ),
    )


def _trade_ready_tuning_response() -> SwingBacktestResponse:
    response = _response()
    return SwingBacktestResponse(
        setup=response.setup,
        start_date=response.start_date,
        end_date=response.end_date,
        initial_capital=response.initial_capital,
        cost_bps=response.cost_bps,
        final_equity=response.final_equity,
        total_return_pct=response.total_return_pct,
        max_drawdown_pct=response.max_drawdown_pct,
        trade_count=60,
        win_rate_pct=response.win_rate_pct,
        avg_trade_return_pct=response.avg_trade_return_pct,
        profit_factor=response.profit_factor,
        exposure_pct=response.exposure_pct,
        skipped_no_cash=0,
        skipped_duplicate=0,
        skipped_no_forward_data=0,
        skipped_by_regime=0,
        attribution_summary=SwingBacktestAttributionSummary(
            sample_quality=SampleQuality(
                status="TRADE_READY",
                completed_trade_count=60,
                candidate_observation_count=0,
                min_sample_size=30,
                trade_sample_ready=True,
                candidate_sample_ready=False,
                notes=(),
            ),
            group_stats=(
                AttributionGroupStat(
                    dimension="signal_strength",
                    bucket="STRONG",
                    trade_count=30,
                    win_rate_pct=20.0,
                    avg_return_pct=-2.0,
                    total_pnl=Decimal("-6000"),
                    profit_factor=0.5,
                ),
                AttributionGroupStat(
                    dimension="signal_strength",
                    bucket="WEAK",
                    trade_count=30,
                    win_rate_pct=80.0,
                    avg_return_pct=5.0,
                    total_pnl=Decimal("15000"),
                    profit_factor=2.0,
                ),
            ),
        ),
    )


def test_display_swing_backtest_hides_attribution_by_default(capsys):
    display_swing_backtest(_response(), show_trades=0)

    output = capsys.readouterr().out
    assert "TUNING ATTRIBUTION SUMMARY" not in output
    assert "TUNING READINESS" not in output
    assert "TUNING READINESS PLAN" not in output
    assert "TUNING PROPOSAL DRAFT" not in output
    assert "TUNING CONFIG DIFF DRAFT" not in output


def test_display_swing_backtest_can_show_attribution_panel(capsys):
    display_swing_backtest(_response(), show_trades=0, show_attribution=True)

    output = capsys.readouterr().out
    assert "TUNING READINESS" in output
    assert "INSUFFICIENT_SAMPLE" in output
    assert "Completed Trades" in output
    assert "Candidate Observations" in output
    assert "TUNING ATTRIBUTION SUMMARY" in output
    assert "learning_summary_only_not_entry_logic" in output
    assert "signal_strength" in output
    assert "signal_score_bucket" in output
    assert "candidate_setup_match" in output
    assert "STRONG" in output


def test_display_swing_backtest_shows_candidate_only_attribution(capsys):
    display_swing_backtest(
        _candidate_only_response(),
        show_trades=0,
        show_attribution=True,
    )

    output = capsys.readouterr().out
    assert "TUNING READINESS" in output
    assert "TUNING ATTRIBUTION SUMMARY" in output
    assert "candidate_setup_match" in output
    assert "NO_MATCH" in output


def test_display_swing_backtest_can_show_tuning_plan(capsys):
    display_swing_backtest(
        _response(),
        show_trades=0,
        show_tuning_plan=True,
    )

    output = capsys.readouterr().out
    assert "TUNING READINESS PLAN" in output
    assert "INSUFFICIENT_SAMPLE" in output
    assert "Can Propose Changes" in output
    assert "Blocked Reasons" in output
    assert "readiness_gate_for_future_tuning_only" in output


def test_display_swing_backtest_can_show_tuning_proposal(capsys):
    display_swing_backtest(
        _response(),
        show_trades=0,
        show_tuning_proposal=True,
    )

    output = capsys.readouterr().out
    assert "TUNING PROPOSAL DRAFT" in output
    assert "BLOCKED" in output
    assert "Candidate Changes" in output
    assert "Rejected Changes" in output
    assert "dry_run_tuning_proposal_contract_only" in output


def test_display_swing_backtest_can_show_tuning_config_diff(capsys):
    display_swing_backtest(
        _response(),
        show_trades=0,
        show_tuning_diff=True,
    )

    output = capsys.readouterr().out
    assert "TUNING CONFIG DIFF DRAFT" in output
    assert "BLOCKED" in output
    assert "Diff Items" in output
    assert "Rejected Items" in output
    assert "config_diff_schema_only_no_apply" in output
    assert "Policy" in output
    assert "Meaning" in output
    assert "INSUFFICIENT_EVIDENCE" in output
    assert "not resolved; readiness blocked" in output


def test_display_swing_backtest_tuning_config_diff_shows_candidate_policy(capsys):
    display_swing_backtest(
        _trade_ready_tuning_response(),
        show_trades=0,
        show_tuning_diff=True,
    )

    output = capsys.readouterr().out
    assert "Resolved Candidates" in output
    assert "Rejected Candidates" in output
    assert "PROPOSED_VALUES_DRY_RUN" in output
    assert "PROPOSED_VALUE_SELECTED" in output
    assert "Item Statuses" in output
    assert "DETERMINISTIC_VALUE_SELECTED" in output
    assert "proposed guarded value" in output
    assert "Value Policies" in output
    assert "Current Only" in output
    assert "Evidence Coverage" in output
    assert "Proposed" in output
    assert "DETERMINISTIC_GUARDED" not in output
