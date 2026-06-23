"""
Tests for Backtest use case.

These tests use mock repository to verify:
- Use case orchestration (rules + indicators + backtest engine)
- Request/response DTOs
- Error handling
- Signal mapping (defaults and custom)
- Integration with YamlConfigLoader and BacktestEngine

All tests run offline with no external dependencies.
"""

import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.use_case.backtest_use_case import (
    BacktestRequest,
    BacktestResponse,
    BacktestUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository

# ============================================================================
# Test Fixtures
# ============================================================================


def make_candle(ticker: str, days_ago: int, price: str = "1000.00") -> Candle:
    """Create a test candle with consistent prices."""
    price_dec = Decimal(price)
    return Candle(
        ticker=ticker,
        date=date.today() - timedelta(days=days_ago),
        open=price_dec,
        high=price_dec + Decimal("10"),
        low=price_dec - Decimal("10"),
        close=price_dec,
        volume=100000,
    )


def make_trending_candles(
    ticker: str,
    count: int,
    start_price: float = 1000.0,
    trend: float = 10.0,
) -> list[Candle]:
    """Create candles with a price trend for realistic indicator testing."""
    candles = []
    for i in range(count - 1, -1, -1):
        price = Decimal(str(start_price + (count - 1 - i) * trend))
        candles.append(
            Candle(
                ticker=ticker,
                date=date.today() - timedelta(days=i),
                open=price,
                high=price + Decimal("20"),
                low=price - Decimal("20"),
                close=price,
                volume=100000,
            )
        )
    return candles


def make_oscillating_candles(
    ticker: str,
    count: int,
    base_price: float = 1000.0,
    amplitude: float = 100.0,
) -> list[Candle]:
    """Create oscillating candles to trigger RSI oversold/overbought."""
    import math

    candles = []
    for i in range(count - 1, -1, -1):
        # Use sine wave to create oscillation
        phase = (count - 1 - i) / 10 * math.pi
        price = Decimal(str(base_price + amplitude * math.sin(phase)))
        candles.append(
            Candle(
                ticker=ticker,
                date=date.today() - timedelta(days=i),
                open=price,
                high=price + Decimal("20"),
                low=price - Decimal("20"),
                close=price,
                volume=100000,
            )
        )
    return candles


class MockRepository(MarketDataRepository):
    """Mock repository for testing."""

    def __init__(self, candles: list[Candle] | None = None):
        self._candles = candles or []

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        days: int | None = None,
    ) -> list[Candle]:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date:
            filtered = [c for c in filtered if c.date >= start_date]
        if end_date:
            filtered = [c for c in filtered if c.date <= end_date]
        return sorted(filtered, key=lambda c: c.date)

    def save_candles(self, candles: list[Candle]) -> None:
        pass

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        return len(self._candles) > 0

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if not filtered:
            return None
        sorted_candles = sorted(filtered, key=lambda c: c.date)
        return (sorted_candles[0].date, sorted_candles[-1].date)


def create_temp_rules_file(content: str) -> Path:
    """Create a temporary YAML rules file."""
    temp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    )
    temp_file.write(content)
    temp_file.close()
    return Path(temp_file.name)


# ============================================================================
# Sample YAML Rules for Testing
# ============================================================================

SIMPLE_RSI_RULES = """
version: 1
name: "simple_rsi"
description: "Simple RSI-based strategy"
default_outcome: MODERATE

rules:
  - name: "oversold_buy"
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI indicates oversold conditions"

  - name: "overbought_sell"
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI indicates overbought conditions"
"""

RSI_RULES_WITH_SIGNAL_MAPPING = """
version: 1
name: "rsi_with_mapping"
description: "RSI strategy with custom signal mapping"
default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: "oversold_buy"
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK

  - name: "overbought_sell"
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
"""

ALWAYS_BUY_RULES = """
version: 1
name: "always_buy"
description: "Always signals buy (for testing)"
default_outcome: LOW_RISK

rules:
  - name: "always_buy"
    priority: 1
    when:
      indicator: RSI
      operator: ">="
      value: 0
    outcome: LOW_RISK
"""


# ============================================================================
# Tests
# ============================================================================


class TestBacktestUseCaseBasics:
    """Test basic BacktestUseCase functionality."""

    def test_execute_returns_backtest_response(self):
        """Should return BacktestResponse for valid inputs."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)
        try:
            request = BacktestRequest(
                ticker="BBCA",
                rules_file=rules_file,
                initial_capital=Decimal("100000000"),
            )
            response = use_case.execute(request)

            assert isinstance(response, BacktestResponse)
            assert response.ticker == "BBCA"
            assert response.result is not None
            assert response.result.strategy_name == "simple_rsi"
        finally:
            rules_file.unlink()

    def test_execute_with_empty_ticker_raises_error(self):
        """Should raise ValueError for empty ticker."""
        repository = MockRepository([])
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)
        try:
            request = BacktestRequest(ticker="", rules_file=rules_file)

            with pytest.raises(ValueError, match="Ticker cannot be empty"):
                use_case.execute(request)
        finally:
            rules_file.unlink()

    def test_execute_with_no_data_raises_error(self):
        """Should raise ValueError when no data available."""
        repository = MockRepository([])  # Empty repository
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)
        try:
            request = BacktestRequest(ticker="BBCA", rules_file=rules_file)

            with pytest.raises(ValueError, match="No data available"):
                use_case.execute(request)
        finally:
            rules_file.unlink()


class TestBacktestUseCaseDateFiltering:
    """Test date filtering in BacktestUseCase."""

    def test_execute_with_start_date(self):
        """Should filter candles by start date."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)
        try:
            # Use start date 30 days ago
            start = date.today() - timedelta(days=30)
            request = BacktestRequest(
                ticker="BBCA",
                rules_file=rules_file,
                start_date=start,
            )
            response = use_case.execute(request)

            # Result start date should be >= requested start
            assert response.result.start_date >= start
        finally:
            rules_file.unlink()

    def test_execute_with_date_range(self):
        """Should filter candles by date range."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)
        try:
            start = date.today() - timedelta(days=50)
            end = date.today() - timedelta(days=10)
            request = BacktestRequest(
                ticker="BBCA",
                rules_file=rules_file,
                start_date=start,
                end_date=end,
            )
            response = use_case.execute(request)

            assert response.result.start_date >= start
            assert response.result.end_date <= end
        finally:
            rules_file.unlink()


class TestBacktestUseCaseSignalMapping:
    """Test signal mapping behavior."""

    def test_default_signal_mapping_used_when_not_specified(self):
        """Should use default signal mapping when not in YAML."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)  # No signal_mapping
        try:
            request = BacktestRequest(ticker="BBCA", rules_file=rules_file)
            response = use_case.execute(request)

            # Should still work with defaults
            assert response.result is not None
        finally:
            rules_file.unlink()

    def test_custom_signal_mapping_from_yaml(self):
        """Should use signal mapping from YAML file."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(RSI_RULES_WITH_SIGNAL_MAPPING)
        try:
            request = BacktestRequest(ticker="BBCA", rules_file=rules_file)
            response = use_case.execute(request)

            # Strategy name from YAML with signal mapping
            assert response.result.strategy_name == "rsi_with_mapping"
        finally:
            rules_file.unlink()


class TestBacktestUseCaseMetrics:
    """Test that use case returns correct metrics."""

    def test_response_has_convenience_properties(self):
        """Response should expose metrics via convenience properties."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)
        try:
            request = BacktestRequest(
                ticker="BBCA",
                rules_file=rules_file,
                initial_capital=Decimal("100000000"),
            )
            response = use_case.execute(request)

            # These should not raise
            _ = response.total_return_pct
            _ = response.trade_count
            _ = response.win_rate
            _ = response.profit_factor
            _ = response.max_drawdown_pct
        finally:
            rules_file.unlink()

    def test_initial_capital_preserved_with_hold_only(self):
        """Capital should be unchanged if strategy only holds."""
        # Use rules that produce MODERATE (HOLD) for all conditions
        moderate_rules = """
version: 1
name: "always_hold"
description: "Always holds"
default_outcome: MODERATE

rules:
  - name: "never_match"
    when:
      indicator: RSI
      operator: "<"
      value: -999
    outcome: LOW_RISK
"""
        candles = make_trending_candles("BBCA", 50)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(moderate_rules)
        try:
            initial = Decimal("100000000")
            request = BacktestRequest(
                ticker="BBCA",
                rules_file=rules_file,
                initial_capital=initial,
            )
            response = use_case.execute(request)

            # No trades should mean capital unchanged
            assert response.result.trade_count == 0
            assert response.result.final_capital == initial
        finally:
            rules_file.unlink()


class TestBacktestUseCaseDeterminism:
    """Test that backtest is deterministic."""

    def test_same_input_same_output(self):
        """Running twice with same input should give identical results."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        rules_file = create_temp_rules_file(SIMPLE_RSI_RULES)
        try:
            request = BacktestRequest(
                ticker="BBCA",
                rules_file=rules_file,
                initial_capital=Decimal("100000000"),
            )

            response1 = use_case.execute(request)
            response2 = use_case.execute(request)

            # Results should be identical
            assert response1.result.final_capital == response2.result.final_capital
            assert response1.result.trade_count == response2.result.trade_count
            assert response1.result.total_return_pct == response2.result.total_return_pct
            assert response1.result.max_drawdown_pct == response2.result.max_drawdown_pct
        finally:
            rules_file.unlink()


class TestBacktestUseCaseErrorHandling:
    """Test error handling in BacktestUseCase."""

    def test_invalid_rules_file_raises_error(self):
        """Should raise error for non-existent rules file."""
        repository = MockRepository([])
        use_case = BacktestUseCase(repository)

        request = BacktestRequest(
            ticker="BBCA",
            rules_file=Path("/nonexistent/rules.yaml"),
        )

        with pytest.raises(Exception):  # RulesFileError
            use_case.execute(request)

    def test_invalid_yaml_syntax_raises_error(self):
        """Should raise error for invalid YAML syntax."""
        candles = make_trending_candles("BBCA", 50)
        repository = MockRepository(candles)
        use_case = BacktestUseCase(repository)

        bad_yaml = "this: is: not: valid: yaml: {"
        rules_file = create_temp_rules_file(bad_yaml)
        try:
            request = BacktestRequest(ticker="BBCA", rules_file=rules_file)

            with pytest.raises(Exception):  # RulesSchemaError
                use_case.execute(request)
        finally:
            rules_file.unlink()
