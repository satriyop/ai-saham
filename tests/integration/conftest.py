"""
Shared fixtures for integration tests.

Provides:
- Temporary workspace management
- Realistic mock candle generation with predictable patterns
- Registry setup with custom formulas
"""

import math
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.indicator_registry import IndicatorRegistry
from src.domain.entities.candle import Candle
from src.infrastructure.persistence.formula_storage import FormulaStorage


# --- Workspace Fixtures ---


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create isolated workspace with strategies/ and formulas."""
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    return tmp_path


@pytest.fixture
def temp_dir() -> Path:
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def formulas_path(temp_dir: Path) -> Path:
    """Create temporary formulas file path."""
    return temp_dir / "formulas.yaml"


@pytest.fixture
def storage(formulas_path: Path) -> FormulaStorage:
    """Create storage with temp path."""
    return FormulaStorage(path=formulas_path)


# --- Candle Generation ---


@dataclass
class CandlePattern:
    """Configuration for candle pattern generation."""

    days: int = 100
    start_price: Decimal = Decimal("10000")
    volatility: float = 0.02
    trend_strength: float = 0.3


def generate_test_candles(
    days: int = 100,
    start_price: Decimal = Decimal("10000"),
    volatility: float = 0.02,
    trend_strength: float = 0.3,
    ticker: str = "TEST",
    start_date: date | None = None,
) -> list[Candle]:
    """Generate realistic candles with known patterns.

    Generates data with:
    - Uptrend in first third (creates RSI overbought around day 30)
    - Downtrend in middle third (creates RSI oversold around day 60)
    - Recovery in last third (moderate RSI)

    This creates predictable RSI oversold/overbought conditions
    for testing strategy signals.

    Args:
        days: Number of candles to generate (default 100)
        start_price: Initial price (default 10000)
        volatility: Daily volatility factor (default 0.02 = 2%)
        trend_strength: How strong the trend phases are (default 0.3)
        ticker: Stock ticker symbol (default "TEST")
        start_date: First date (default: 100 days ago from 2024-06-01)

    Returns:
        List of Candle objects sorted by date ascending
    """
    if start_date is None:
        # Use a fixed date for reproducibility
        start_date = date(2024, 3, 1)

    candles = []
    price = float(start_price)

    # Phase boundaries
    phase_1_end = days // 3  # Uptrend
    phase_2_end = 2 * days // 3  # Downtrend

    for i in range(days):
        current_date = start_date + timedelta(days=i)

        # Determine trend based on phase
        if i < phase_1_end:
            # Phase 1: Uptrend (creates overbought conditions)
            trend = trend_strength * 0.01  # +0.3% daily trend
        elif i < phase_2_end:
            # Phase 2: Downtrend (creates oversold conditions)
            trend = -trend_strength * 0.012  # -0.36% daily trend (stronger)
        else:
            # Phase 3: Recovery/consolidation
            trend = trend_strength * 0.005  # +0.15% daily trend (moderate)

        # Add trend and noise
        random_factor = math.sin(i * 0.7) * volatility  # Deterministic "random"
        daily_return = trend + random_factor

        # Calculate OHLC from price
        prev_price = price
        price = price * (1 + daily_return)

        # Generate realistic OHLC
        open_price = Decimal(str(round(prev_price, 2)))
        close_price = Decimal(str(round(price, 2)))

        # High is max of open/close plus some noise
        high_offset = abs(random_factor) + volatility * 0.5
        high_price = max(open_price, close_price) * Decimal(str(1 + high_offset))

        # Low is min of open/close minus some noise
        low_offset = abs(math.sin((i + 10) * 0.5)) * volatility * 0.8
        low_price = min(open_price, close_price) * Decimal(str(1 - low_offset))

        # Ensure price constraints
        if high_price < low_price:
            high_price, low_price = low_price, high_price

        # Volume varies with volatility
        base_volume = 100000
        volume = int(base_volume * (1 + abs(random_factor) * 5))

        candle = Candle(
            ticker=ticker,
            date=current_date,
            open=Decimal(str(round(float(open_price), 2))),
            high=Decimal(str(round(float(high_price), 2))),
            low=Decimal(str(round(float(low_price), 2))),
            close=Decimal(str(round(float(close_price), 2))),
            volume=volume,
        )
        candles.append(candle)

    return candles


def generate_simple_candles(
    days: int = 50,
    ticker: str = "TEST",
    start_date: date | None = None,
) -> list[Candle]:
    """Generate simple linear candles for basic testing.

    Creates a simple upward trend with consistent increments.
    Useful for tests that need predictable indicator values.

    Args:
        days: Number of candles
        ticker: Stock symbol
        start_date: First date

    Returns:
        List of Candle objects
    """
    if start_date is None:
        start_date = date(2024, 1, 1)

    return [
        Candle(
            ticker=ticker,
            date=start_date + timedelta(days=i),
            open=Decimal(f"{1000 + i * 10}"),
            high=Decimal(f"{1100 + i * 10}"),
            low=Decimal(f"{900 + i * 10}"),
            close=Decimal(f"{1050 + i * 10}"),
            volume=100000 + i * 1000,
        )
        for i in range(days)
    ]


@pytest.fixture
def mock_candles() -> list[Candle]:
    """Generate realistic test candles for backtesting.

    Returns 100 days of data with uptrend/downtrend/recovery phases.
    """
    return generate_test_candles(days=100)


@pytest.fixture
def simple_candles() -> list[Candle]:
    """Generate simple candles for basic testing.

    Returns 50 days of simple linear data.
    """
    return generate_simple_candles(days=50)


# --- Registry Fixtures ---


@pytest.fixture
def registry_with_formulas(storage: FormulaStorage) -> IndicatorRegistry:
    """Registry with pre-registered custom formulas.

    Includes:
    - SMOOTH_RSI: SMA(RSI(14), 10)
    - MY_RSI: RSI(14)
    """
    # Save formulas to storage
    storage.save("SMOOTH_RSI", "SMA(RSI(14), 10)", intent="smoothed RSI")
    storage.save("MY_RSI", "RSI(14)", intent="14-day RSI")

    # Create registry with formulas loaded
    registry = create_indicator_registry(
        formula_storage=storage,
        load_formulas=True,
    )

    return registry


@pytest.fixture
def clean_registry() -> IndicatorRegistry:
    """Clean registry with only built-in indicators."""
    return IndicatorRegistry()


# --- Strategy YAML Templates ---


def create_strategy_yaml(
    name: str,
    rules: list[dict],
    indicators: dict | None = None,
    default_outcome: str = "MODERATE",
    signal_mapping: dict | None = None,
) -> str:
    """Create a strategy YAML string.

    Args:
        name: Strategy name
        rules: List of rule definitions
        indicators: Optional custom indicator definitions
        default_outcome: Default outcome when no rules match
        signal_mapping: Optional signal to trade action mapping

    Returns:
        YAML string content
    """
    import yaml

    strategy = {
        "version": 1,
        "name": name,
        "default_outcome": default_outcome,
        "rules": rules,
    }

    if indicators:
        strategy["indicators"] = indicators

    if signal_mapping:
        strategy["signal_mapping"] = signal_mapping

    return yaml.dump(strategy, default_flow_style=False)


def create_rsi_oversold_strategy(name: str = "rsi_oversold_test") -> str:
    """Create a simple RSI oversold strategy YAML.

    Rules:
    - RSI < 30: LOW_RISK (oversold → buy signal)
    - RSI > 70: HIGH_RISK (overbought → sell signal)
    """
    return create_strategy_yaml(
        name=name,
        rules=[
            {
                "name": "oversold",
                "when": {
                    "indicator": "RSI",
                    "operator": "<",
                    "value": 30,
                },
                "outcome": "LOW_RISK",
                "rationale": "RSI below 30 indicates oversold",
            },
            {
                "name": "overbought",
                "when": {
                    "indicator": "RSI",
                    "operator": ">",
                    "value": 70,
                },
                "outcome": "HIGH_RISK",
                "rationale": "RSI above 70 indicates overbought",
            },
        ],
        signal_mapping={
            "LOW_RISK": "ENTER_LONG",
            "MODERATE": "HOLD",
            "HIGH_RISK": "EXIT_LONG",
        },
    )


def create_custom_indicator_strategy(
    name: str = "smooth_rsi_strategy",
    indicator_name: str = "SMOOTH_RSI",
) -> str:
    """Create a strategy that uses a custom formula indicator.

    Args:
        name: Strategy name
        indicator_name: Name of the custom indicator to use

    Returns:
        YAML string
    """
    return create_strategy_yaml(
        name=name,
        rules=[
            {
                "name": "oversold_smooth",
                "when": {
                    "indicator": indicator_name,
                    "operator": "<",
                    "value": 35,
                },
                "outcome": "LOW_RISK",
                "rationale": f"{indicator_name} below 35",
            },
            {
                "name": "overbought_smooth",
                "when": {
                    "indicator": indicator_name,
                    "operator": ">",
                    "value": 65,
                },
                "outcome": "HIGH_RISK",
                "rationale": f"{indicator_name} above 65",
            },
        ],
        signal_mapping={
            "LOW_RISK": "ENTER_LONG",
            "MODERATE": "HOLD",
            "HIGH_RISK": "EXIT_LONG",
        },
    )


def create_ema_crossover_strategy(name: str = "ema_crossover") -> str:
    """Create an EMA crossover strategy.

    Uses custom indicator definitions for fast and slow EMA.
    """
    return create_strategy_yaml(
        name=name,
        indicators={
            "fast_ema": {"type": "EMA", "period": 9},
            "slow_ema": {"type": "EMA", "period": 21},
        },
        rules=[
            {
                "name": "bullish_crossover",
                "priority": 10,
                "when": {
                    "left": {"indicator": "fast_ema"},
                    "operator": ">",
                    "right": {"indicator": "slow_ema"},
                },
                "outcome": "LOW_RISK",
                "rationale": "Fast EMA above slow EMA",
            },
            {
                "name": "bearish_crossover",
                "priority": 10,
                "when": {
                    "left": {"indicator": "fast_ema"},
                    "operator": "<",
                    "right": {"indicator": "slow_ema"},
                },
                "outcome": "HIGH_RISK",
                "rationale": "Fast EMA below slow EMA",
            },
        ],
        signal_mapping={
            "LOW_RISK": "ENTER_LONG",
            "MODERATE": "HOLD",
            "HIGH_RISK": "EXIT_LONG",
        },
    )
