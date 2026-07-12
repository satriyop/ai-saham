from datetime import date
from decimal import Decimal

import pytest

from src.domain.services.backtest_engine import BacktestEngine
from src.domain.value_objects.trade_action import TradeAction
from tests.domain.backtest_engine_fixtures import make_candle, make_candles


class TestBacktestEngineCreation:
    """Test BacktestEngine initialization."""

    def test_create_with_valid_capital(self):
        """Engine should be created with valid capital."""
        assert BacktestEngine(Decimal("100000")) is not None
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
