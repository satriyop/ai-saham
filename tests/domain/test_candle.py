"""
Tests for Candle entity.

These tests verify:
- Candle creation and validation
- Serialization/deserialization
- Edge cases and error handling

All tests run offline with no external dependencies.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.domain.entities.candle import Candle


class TestCandleCreation:
    """Test Candle entity creation."""

    def test_create_valid_candle(self):
        """Valid candle should be created successfully."""
        candle = Candle(
            ticker="BBCA",
            date=date(2024, 1, 15),
            open=Decimal("9500.00"),
            high=Decimal("9600.00"),
            low=Decimal("9400.00"),
            close=Decimal("9550.00"),
            volume=1000000,
        )

        assert candle.ticker == "BBCA"
        assert candle.date == date(2024, 1, 15)
        assert candle.open == Decimal("9500.00")
        assert candle.high == Decimal("9600.00")
        assert candle.low == Decimal("9400.00")
        assert candle.close == Decimal("9550.00")
        assert candle.volume == 1000000

    def test_candle_is_immutable(self):
        """Candle should be immutable (frozen dataclass)."""
        candle = Candle(
            ticker="BBCA",
            date=date(2024, 1, 15),
            open=Decimal("9500.00"),
            high=Decimal("9600.00"),
            low=Decimal("9400.00"),
            close=Decimal("9550.00"),
            volume=1000000,
        )

        with pytest.raises(AttributeError):
            candle.close = Decimal("9999.00")


class TestCandleValidation:
    """Test Candle validation rules."""

    def test_empty_ticker_raises_error(self):
        """Empty ticker should raise ValueError."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            Candle(
                ticker="",
                date=date(2024, 1, 15),
                open=Decimal("9500.00"),
                high=Decimal("9600.00"),
                low=Decimal("9400.00"),
                close=Decimal("9550.00"),
                volume=1000000,
            )

    def test_high_less_than_low_raises_error(self):
        """High price less than low should raise ValueError."""
        with pytest.raises(ValueError, match="High price cannot be less than low"):
            Candle(
                ticker="BBCA",
                date=date(2024, 1, 15),
                open=Decimal("9500.00"),
                high=Decimal("9300.00"),  # Less than low
                low=Decimal("9400.00"),
                close=Decimal("9550.00"),
                volume=1000000,
            )

    def test_negative_price_raises_error(self):
        """Negative prices should raise ValueError."""
        with pytest.raises(ValueError, match="Prices cannot be negative"):
            Candle(
                ticker="BBCA",
                date=date(2024, 1, 15),
                open=Decimal("-100.00"),
                high=Decimal("9600.00"),
                low=Decimal("9400.00"),
                close=Decimal("9550.00"),
                volume=1000000,
            )

    def test_negative_volume_raises_error(self):
        """Negative volume should raise ValueError."""
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            Candle(
                ticker="BBCA",
                date=date(2024, 1, 15),
                open=Decimal("9500.00"),
                high=Decimal("9600.00"),
                low=Decimal("9400.00"),
                close=Decimal("9550.00"),
                volume=-1000,
            )

    def test_zero_volume_is_valid(self):
        """Zero volume should be allowed (e.g., trading halt)."""
        candle = Candle(
            ticker="BBCA",
            date=date(2024, 1, 15),
            open=Decimal("9500.00"),
            high=Decimal("9600.00"),
            low=Decimal("9400.00"),
            close=Decimal("9550.00"),
            volume=0,
        )
        assert candle.volume == 0


class TestCandleSerialization:
    """Test Candle serialization."""

    def test_to_dict(self):
        """Candle should serialize to dictionary."""
        candle = Candle(
            ticker="BBCA",
            date=date(2024, 1, 15),
            open=Decimal("9500.00"),
            high=Decimal("9600.00"),
            low=Decimal("9400.00"),
            close=Decimal("9550.00"),
            volume=1000000,
        )

        result = candle.to_dict()

        assert result == {
            "ticker": "BBCA",
            "date": "2024-01-15",
            "open": "9500.00",
            "high": "9600.00",
            "low": "9400.00",
            "close": "9550.00",
            "volume": 1000000,
        }

    def test_from_dict(self):
        """Candle should deserialize from dictionary."""
        data = {
            "ticker": "BBCA",
            "date": "2024-01-15",
            "open": "9500.00",
            "high": "9600.00",
            "low": "9400.00",
            "close": "9550.00",
            "volume": 1000000,
        }

        candle = Candle.from_dict(data)

        assert candle.ticker == "BBCA"
        assert candle.date == date(2024, 1, 15)
        assert candle.open == Decimal("9500.00")
        assert candle.volume == 1000000

    def test_roundtrip_serialization(self):
        """Candle should survive roundtrip serialization."""
        original = Candle(
            ticker="BBCA",
            date=date(2024, 1, 15),
            open=Decimal("9500.00"),
            high=Decimal("9600.00"),
            low=Decimal("9400.00"),
            close=Decimal("9550.00"),
            volume=1000000,
        )

        restored = Candle.from_dict(original.to_dict())

        assert restored == original
