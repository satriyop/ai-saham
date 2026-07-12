from datetime import date
from decimal import Decimal

import pytest

from src.domain.entities.backtest_trade import BacktestTrade


class TestBacktestTradeCreation:
    """Test BacktestTrade entity creation."""

    def test_create_valid_trade(self):
        """Valid trade should be created successfully."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy_signal",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1100"),
            exit_rule="sell_signal",
            shares=100,
        )

        assert trade.entry_date == date(2024, 1, 1)
        assert trade.entry_price == Decimal("1000")
        assert trade.entry_rule == "buy_signal"
        assert trade.exit_date == date(2024, 1, 10)
        assert trade.exit_price == Decimal("1100")
        assert trade.exit_rule == "sell_signal"
        assert trade.shares == 100

    def test_trade_is_immutable(self):
        """BacktestTrade should be immutable (frozen dataclass)."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy_signal",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1100"),
            exit_rule="sell_signal",
            shares=100,
        )

        with pytest.raises(AttributeError):
            trade.shares = 200


class TestBacktestTradeValidation:
    """Test BacktestTrade validation rules."""

    def test_zero_entry_price_raises_error(self):
        """Zero entry price should raise ValueError."""
        with pytest.raises(ValueError, match="Entry price must be positive"):
            BacktestTrade(
                entry_date=date(2024, 1, 1),
                entry_price=Decimal("0"),
                entry_rule="buy_signal",
                exit_date=date(2024, 1, 10),
                exit_price=Decimal("1100"),
                exit_rule="sell_signal",
                shares=100,
            )

    def test_negative_exit_price_raises_error(self):
        """Negative exit price should raise ValueError."""
        with pytest.raises(ValueError, match="Exit price must be positive"):
            BacktestTrade(
                entry_date=date(2024, 1, 1),
                entry_price=Decimal("1000"),
                entry_rule="buy_signal",
                exit_date=date(2024, 1, 10),
                exit_price=Decimal("-100"),
                exit_rule="sell_signal",
                shares=100,
            )

    def test_zero_shares_raises_error(self):
        """Zero shares should raise ValueError."""
        with pytest.raises(ValueError, match="Shares must be positive"):
            BacktestTrade(
                entry_date=date(2024, 1, 1),
                entry_price=Decimal("1000"),
                entry_rule="buy_signal",
                exit_date=date(2024, 1, 10),
                exit_price=Decimal("1100"),
                exit_rule="sell_signal",
                shares=0,
            )

    def test_exit_before_entry_raises_error(self):
        """Exit date before entry date should raise ValueError."""
        with pytest.raises(ValueError, match="Exit date cannot be before entry date"):
            BacktestTrade(
                entry_date=date(2024, 1, 10),
                entry_price=Decimal("1000"),
                entry_rule="buy_signal",
                exit_date=date(2024, 1, 1),
                exit_price=Decimal("1100"),
                exit_rule="sell_signal",
                shares=100,
            )

    def test_empty_entry_rule_raises_error(self):
        """Empty entry rule should raise ValueError."""
        with pytest.raises(ValueError, match="Entry rule cannot be empty"):
            BacktestTrade(
                entry_date=date(2024, 1, 1),
                entry_price=Decimal("1000"),
                entry_rule="",
                exit_date=date(2024, 1, 10),
                exit_price=Decimal("1100"),
                exit_rule="sell_signal",
                shares=100,
            )


class TestBacktestTradeComputedProperties:
    """Test BacktestTrade computed properties."""

    def test_pnl_for_winning_trade(self):
        """P&L should be positive for winning trade."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=100,
        )

        # (1100 - 1000) * 100 = 10,000
        assert trade.pnl == Decimal("10000")

    def test_pnl_for_losing_trade(self):
        """P&L should be negative for losing trade."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("900"),
            exit_rule="sell",
            shares=100,
        )

        # (900 - 1000) * 100 = -10,000
        assert trade.pnl == Decimal("-10000")

    def test_pnl_percent(self):
        """P&L percent should be calculated correctly."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=100,
        )

        # ((1100 - 1000) / 1000) * 100 = 10%
        assert trade.pnl_percent == Decimal("10")

    def test_holding_days(self):
        """Holding days should be calculated correctly."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=100,
        )

        assert trade.holding_days == 9

    def test_same_day_trade(self):
        """Same-day trade should have 0 holding days."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 1),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=100,
        )

        assert trade.holding_days == 0

    def test_is_winning_true(self):
        """is_winning should be True for profitable trade."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1100"),
            exit_rule="sell",
            shares=100,
        )

        assert trade.is_winning is True

    def test_is_winning_false(self):
        """is_winning should be False for losing trade."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("900"),
            exit_rule="sell",
            shares=100,
        )

        assert trade.is_winning is False

    def test_breakeven_is_not_winning(self):
        """Break-even trade should not be considered winning."""
        trade = BacktestTrade(
            entry_date=date(2024, 1, 1),
            entry_price=Decimal("1000"),
            entry_rule="buy",
            exit_date=date(2024, 1, 10),
            exit_price=Decimal("1000"),
            exit_rule="sell",
            shares=100,
        )

        assert trade.is_winning is False
        assert trade.pnl == Decimal("0")
