from datetime import date
from decimal import Decimal

from src.adapters.cli.trade_swing_display import display_swing_backtest
from src.application.services.swing_backtest_attribution import (
    AttributionGroupStat,
    CandidateAttributionStat,
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


def test_display_swing_backtest_hides_attribution_by_default(capsys):
    display_swing_backtest(_response(), show_trades=0)

    output = capsys.readouterr().out
    assert "TUNING ATTRIBUTION SUMMARY" not in output
    assert "TUNING READINESS" not in output
    assert "TUNING READINESS PLAN" not in output
    assert "TUNING PROPOSAL DRAFT" not in output


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
