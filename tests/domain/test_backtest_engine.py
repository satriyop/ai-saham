"""
Tests for backtest domain components.

These tests verify:
- BacktestTrade entity creation and computed properties
- BacktestResult value object creation and metrics
- BacktestEngine simulation logic
- Edge cases and error handling

All tests run offline with no external dependencies.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.domain.entities.backtest_trade import BacktestTrade
from src.domain.entities.candle import Candle
from src.domain.services.backtest_engine import BacktestEngine
from src.domain.value_objects.backtest_result import BacktestResult
from src.domain.value_objects.trade_action import TradeAction

# ============================================================================
# Test Helpers
# ============================================================================


def make_candle(
    ticker: str = "BBCA",
    candle_date: date = date(2024, 1, 1),
    close: Decimal = Decimal("1000"),
) -> Candle:
    """Create a test candle with sensible defaults."""
    return Candle(
        ticker=ticker,
        date=candle_date,
        open=close,
        high=close + Decimal("10"),
        low=close - Decimal("10"),
        close=close,
        volume=100000,
    )


def make_candles(
    ticker: str = "BBCA",
    count: int = 10,
    start_price: Decimal = Decimal("1000"),
    price_increment: Decimal = Decimal("10"),
) -> list[Candle]:
    """Create a list of test candles with incrementing prices."""
    candles = []
    for i in range(count):
        price = start_price + (price_increment * i)
        candles.append(
            make_candle(
                ticker=ticker,
                candle_date=date(2024, 1, i + 1),
                close=price,
            )
        )
    return candles


# ============================================================================
# BacktestTrade Tests
# ============================================================================


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


# ============================================================================
# BacktestResult Tests
# ============================================================================


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


# ============================================================================
# BacktestEngine Tests
# ============================================================================


class TestBacktestEngineCreation:
    """Test BacktestEngine initialization."""

    def test_create_with_valid_capital(self):
        """Engine should be created with valid capital."""
        engine = BacktestEngine(Decimal("100000"))
        # No exception means success

    def test_zero_capital_raises_error(self):
        """Zero initial capital should raise ValueError."""
        with pytest.raises(ValueError, match="Initial capital must be positive"):
            BacktestEngine(Decimal("0"))

    def test_negative_capital_raises_error(self):
        """Negative initial capital should raise ValueError."""
        with pytest.raises(ValueError, match="Initial capital must be positive"):
            BacktestEngine(Decimal("-10000"))


class TestBacktestEngineRun:
    """Test BacktestEngine.run() method."""

    def test_empty_candles_raises_error(self):
        """Empty candles should raise ValueError."""
        engine = BacktestEngine(Decimal("100000"))

        with pytest.raises(ValueError, match="Cannot run backtest with empty candles"):
            engine.run([], [], "test_strategy")

    def test_empty_strategy_name_raises_error(self):
        """Empty strategy name should raise ValueError."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=5)

        with pytest.raises(ValueError, match="Strategy name cannot be empty"):
            engine.run(candles, [], "")

    def test_hold_only_no_trades(self):
        """HOLD actions only should result in no trades."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=5)
        actions = [(c.date, TradeAction.HOLD, "hold_rule") for c in candles]

        result = engine.run(candles, actions, "hold_strategy")

        assert result.trade_count == 0
        assert result.final_capital == Decimal("100000")

    def test_single_entry_exit(self):
        """Single ENTER_LONG followed by EXIT_LONG should create one trade."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=5, start_price=Decimal("1000"))

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy_rule"),
            (candles[1].date, TradeAction.HOLD, "hold"),
            (candles[2].date, TradeAction.HOLD, "hold"),
            (candles[3].date, TradeAction.EXIT_LONG, "sell_rule"),
            (candles[4].date, TradeAction.HOLD, "hold"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        assert result.trade_count == 1
        assert result.trades[0].entry_rule == "buy_rule"
        assert result.trades[0].exit_rule == "sell_rule"

    def test_entry_without_exit_forces_close(self):
        """Entry without exit should force close at end of data."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=5)

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy_rule"),
            (candles[1].date, TradeAction.HOLD, "hold"),
            (candles[2].date, TradeAction.HOLD, "hold"),
            (candles[3].date, TradeAction.HOLD, "hold"),
            (candles[4].date, TradeAction.HOLD, "hold"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        assert result.trade_count == 1
        assert result.trades[0].exit_rule == "end_of_data"
        assert result.trades[0].exit_date == candles[-1].date

    def test_multiple_trades(self):
        """Multiple entry/exit cycles should create multiple trades."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=10)

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy1"),
            (candles[1].date, TradeAction.EXIT_LONG, "sell1"),
            (candles[2].date, TradeAction.HOLD, "hold"),
            (candles[3].date, TradeAction.ENTER_LONG, "buy2"),
            (candles[4].date, TradeAction.EXIT_LONG, "sell2"),
            (candles[5].date, TradeAction.HOLD, "hold"),
            (candles[6].date, TradeAction.ENTER_LONG, "buy3"),
            (candles[7].date, TradeAction.EXIT_LONG, "sell3"),
            (candles[8].date, TradeAction.HOLD, "hold"),
            (candles[9].date, TradeAction.HOLD, "hold"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        assert result.trade_count == 3

    def test_double_entry_ignored(self):
        """Second ENTER_LONG while in position should be ignored."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=5)

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy1"),
            (candles[1].date, TradeAction.ENTER_LONG, "buy2"),  # Should be ignored
            (candles[2].date, TradeAction.ENTER_LONG, "buy3"),  # Should be ignored
            (candles[3].date, TradeAction.EXIT_LONG, "sell"),
            (candles[4].date, TradeAction.HOLD, "hold"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        assert result.trade_count == 1
        assert result.trades[0].entry_rule == "buy1"  # First entry used

    def test_exit_without_position_ignored(self):
        """EXIT_LONG without position should be ignored."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=5)

        actions = [
            (candles[0].date, TradeAction.EXIT_LONG, "sell1"),  # No position - ignored
            (candles[1].date, TradeAction.EXIT_LONG, "sell2"),  # Still no position
            (candles[2].date, TradeAction.ENTER_LONG, "buy"),
            (candles[3].date, TradeAction.EXIT_LONG, "sell3"),  # Valid exit
            (candles[4].date, TradeAction.HOLD, "hold"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        assert result.trade_count == 1
        assert result.trades[0].exit_rule == "sell3"

    def test_capital_allocation(self):
        """All capital should be used for position (all-in)."""
        initial_capital = Decimal("100000")
        engine = BacktestEngine(initial_capital)

        # Price = 1000, so 100 shares can be bought
        candles = make_candles(count=3, start_price=Decimal("1000"))

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy"),
            (candles[1].date, TradeAction.EXIT_LONG, "sell"),
            (candles[2].date, TradeAction.HOLD, "hold"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        assert result.trades[0].shares == 100

    def test_final_capital_with_profit(self):
        """Final capital should reflect trading profit."""
        engine = BacktestEngine(Decimal("100000"))

        # Buy at 1000, sell at 1100 = 10% profit
        candles = [
            make_candle(candle_date=date(2024, 1, 1), close=Decimal("1000")),
            make_candle(candle_date=date(2024, 1, 2), close=Decimal("1100")),
        ]

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy"),
            (candles[1].date, TradeAction.EXIT_LONG, "sell"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        # 100 shares * (1100 - 1000) = 10,000 profit
        assert result.final_capital == Decimal("110000")


class TestBacktestEngineDrawdown:
    """Test BacktestEngine drawdown calculation."""

    def test_no_drawdown_uptrend(self):
        """Monotonically increasing equity should have zero drawdown."""
        engine = BacktestEngine(Decimal("100000"))

        # Prices increase every day - no drawdown
        candles = make_candles(count=5, start_price=Decimal("1000"), price_increment=Decimal("100"))

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy"),
            (candles[1].date, TradeAction.HOLD, "hold"),
            (candles[2].date, TradeAction.HOLD, "hold"),
            (candles[3].date, TradeAction.HOLD, "hold"),
            (candles[4].date, TradeAction.EXIT_LONG, "sell"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        assert result.max_drawdown_pct == Decimal("0")

    def test_drawdown_calculation(self):
        """Drawdown should be calculated from peak to trough."""
        engine = BacktestEngine(Decimal("100000"))

        # Create candles with a peak and then decline
        candles = [
            make_candle(candle_date=date(2024, 1, 1), close=Decimal("1000")),  # Entry
            make_candle(candle_date=date(2024, 1, 2), close=Decimal("1100")),  # Peak
            make_candle(candle_date=date(2024, 1, 3), close=Decimal("990")),  # Trough
            make_candle(candle_date=date(2024, 1, 4), close=Decimal("1050")),  # Recovery
        ]

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy"),
            (candles[1].date, TradeAction.HOLD, "hold"),
            (candles[2].date, TradeAction.HOLD, "hold"),
            (candles[3].date, TradeAction.EXIT_LONG, "sell"),
        ]

        result = engine.run(candles, actions, "test_strategy")

        # Should have some drawdown from peak
        assert result.max_drawdown_pct > Decimal("0")


class TestBacktestEngineDeterminism:
    """Test that BacktestEngine is deterministic."""

    def test_same_input_same_output(self):
        """Same inputs should always produce same outputs."""
        engine = BacktestEngine(Decimal("100000"))
        candles = make_candles(count=10)

        actions = [
            (candles[0].date, TradeAction.ENTER_LONG, "buy"),
            (candles[3].date, TradeAction.EXIT_LONG, "sell"),
            (candles[6].date, TradeAction.ENTER_LONG, "buy"),
            (candles[9].date, TradeAction.EXIT_LONG, "sell"),
        ]

        # Run twice
        result1 = engine.run(candles, actions, "test_strategy")
        result2 = engine.run(candles, actions, "test_strategy")

        # Results should be identical
        assert result1.final_capital == result2.final_capital
        assert result1.trade_count == result2.trade_count
        assert result1.max_drawdown_pct == result2.max_drawdown_pct
        assert len(result1.trades) == len(result2.trades)
