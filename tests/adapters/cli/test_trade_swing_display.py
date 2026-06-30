from datetime import date
from decimal import Decimal

from src.adapters.cli.trade_swing_display import display_swing_backtest
from src.application.services.swing_backtest_attribution import (
    AttributionGroupStat,
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
            )
        ),
    )


def test_display_swing_backtest_hides_attribution_by_default(capsys):
    display_swing_backtest(_response(), show_trades=0)

    output = capsys.readouterr().out
    assert "TUNING ATTRIBUTION SUMMARY" not in output


def test_display_swing_backtest_can_show_attribution_panel(capsys):
    display_swing_backtest(_response(), show_trades=0, show_attribution=True)

    output = capsys.readouterr().out
    assert "TUNING ATTRIBUTION SUMMARY" in output
    assert "learning_summary_only_not_entry_logic" in output
    assert "signal_strength" in output
    assert "signal_score_bucket" in output
    assert "STRONG" in output
