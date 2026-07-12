from datetime import date
from decimal import Decimal

import pytest

from src.domain.entities.backtest_trade import BacktestTrade
from src.domain.value_objects.backtest_result import BacktestResult


class TestBacktestResultCreation:
    """Test BacktestResult value object creation."""

    def test_create_valid_result(self):
        """Valid result should be created successfully."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=100,
        )

        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("110000"),
            trades=(trade,),
            max_drawdown_pct=Decimal("5"),
        )

        assert result.ticker == "BBCA"
        assert result.strategy_name == "test_strategy"
        assert result.trade_count == 1

    def test_result_is_immutable(self):
        """BacktestResult should be immutable."""
        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("110000"),
            trades=(),
            max_drawdown_pct=Decimal("5"),
        )

        with pytest.raises(AttributeError):
            result.ticker = "BBRI"


class TestBacktestResultValidation:
    """Test BacktestResult validation rules."""

    def test_empty_ticker_raises_error(self):
        """Empty ticker should raise ValueError."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            BacktestResult(
                ticker="",
                strategy_name="test_strategy",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                initial_capital=Decimal("100000"),
                final_capital=Decimal("110000"),
                trades=(),
                max_drawdown_pct=Decimal("5"),
            )

    def test_end_before_start_raises_error(self):
        """End date before start date should raise ValueError."""
        with pytest.raises(ValueError, match="End date cannot be before start date"):
            BacktestResult(
                ticker="BBCA",
                strategy_name="test_strategy",
                start_date=date(2024, 1, 31),
                end_date=date(2024, 1, 1),
                initial_capital=Decimal("100000"),
                final_capital=Decimal("110000"),
                trades=(),
                max_drawdown_pct=Decimal("5"),
            )

    def test_zero_initial_capital_raises_error(self):
        """Zero initial capital should raise ValueError."""
        with pytest.raises(ValueError, match="Initial capital must be positive"):
            BacktestResult(
                ticker="BBCA",
                strategy_name="test_strategy",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                initial_capital=Decimal("0"),
                final_capital=Decimal("110000"),
                trades=(),
                max_drawdown_pct=Decimal("5"),
            )


class TestBacktestResultMetrics:
    """Test BacktestResult computed metrics."""

    def test_total_return_pct_positive(self):
        """Total return should be positive for profitable backtest."""
        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("115000"),
            trades=(),
            max_drawdown_pct=Decimal("5"),
        )

        # ((115000 - 100000) / 100000) * 100 = 15%
        assert result.total_return_pct == Decimal("15")

    def test_total_return_pct_negative(self):
        """Total return should be negative for losing backtest."""
        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("90000"),
            trades=(),
            max_drawdown_pct=Decimal("10"),
        )

        assert result.total_return_pct == Decimal("-10")

    def test_win_rate_calculation(self):
        """Win rate should be calculated correctly."""
        winning_trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 5),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=10,
        )
        losing_trade = BacktestTrade(
            entry_date=date(2024, 1, 10),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 15),
            exit_price=Decimal("900"),
            exit_rule="sell",
            shares=10,
        )

        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("100000"),
            trades=(winning_trade, losing_trade),
            max_drawdown_pct=Decimal("5"),
        )

        # 1 winning out of 2 trades = 50%
        assert result.win_rate == Decimal("50")

    def test_win_rate_zero_trades(self):
        """Win rate should be 0 with no trades."""
        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("100000"),
            trades=(),
            max_drawdown_pct=Decimal("0"),
        )

        assert result.win_rate == Decimal("0")

    def test_profit_factor_calculation(self):
        """Profit factor should be gross profit / gross loss."""
        winning_trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 5),
            exit_price=Decimal("1200"),  # +20%
            exit_rule="sell",
            shares=100,
        )
        losing_trade = BacktestTrade(
            entry_date=date(2024, 1, 10),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 15),
            exit_price=Decimal("900"),  # -10%
            exit_rule="sell",
            shares=100,
        )

        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("110000"),
            trades=(winning_trade, losing_trade),
            max_drawdown_pct=Decimal("5"),
        )

        # Gross profit: 20000, Gross loss: 10000
        # Profit factor: 20000 / 10000 = 2
        assert result.profit_factor == Decimal("2")

    def test_profit_factor_no_losses(self):
        """Profit factor should be high indicator when no losses."""
        winning_trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 5),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=100,
        )

        result = BacktestResult(
            ticker="BBCA",
            strategy_name="test_strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("110000"),
            trades=(winning_trade,),
            max_drawdown_pct=Decimal("0"),
        )

        # All wins, no losses - should return high indicator
        assert result.profit_factor == Decimal("999.99")
