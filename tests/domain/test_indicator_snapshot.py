"""
Tests for IndicatorSnapshot value object.

These tests verify:
- Construction with valid data
- Immutability (frozen dataclass)
- Equality semantics

All tests run offline with no external dependencies.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot


class TestIndicatorSnapshotConstruction:
    """Test IndicatorSnapshot construction."""

    def test_creates_snapshot_with_valid_data(self):
        """Should create snapshot with all indicator values."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("9425.00"),
            ema=Decimal("9418.75"),
            rsi=Decimal("52.34"),
        )

        assert snapshot.date == date(2024, 1, 15)
        assert snapshot.sma == Decimal("9425.00")
        assert snapshot.ema == Decimal("9418.75")
        assert snapshot.rsi == Decimal("52.34")

    def test_creates_snapshot_with_extreme_rsi_values(self):
        """Should accept extreme RSI values (0 and 100)."""
        snapshot_low = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("0"),
        )
        assert snapshot_low.rsi == Decimal("0")

        snapshot_high = IndicatorSnapshot(
            date=date(2024, 1, 16),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("100"),
        )
        assert snapshot_high.rsi == Decimal("100")


class TestIndicatorSnapshotImmutability:
    """Test IndicatorSnapshot immutability."""

    def test_cannot_modify_date(self):
        """Should raise error when modifying date."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            snapshot.date = date(2024, 1, 16)

    def test_cannot_modify_sma(self):
        """Should raise error when modifying sma."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            snapshot.sma = Decimal("200")

    def test_cannot_modify_ema(self):
        """Should raise error when modifying ema."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            snapshot.ema = Decimal("200")

    def test_cannot_modify_rsi(self):
        """Should raise error when modifying rsi."""
        snapshot = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            snapshot.rsi = Decimal("75")


class TestIndicatorSnapshotEquality:
    """Test IndicatorSnapshot equality semantics."""

    def test_equal_snapshots_are_equal(self):
        """Snapshots with same values should be equal."""
        snapshot1 = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("9425.00"),
            ema=Decimal("9418.75"),
            rsi=Decimal("52.34"),
        )
        snapshot2 = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("9425.00"),
            ema=Decimal("9418.75"),
            rsi=Decimal("52.34"),
        )

        assert snapshot1 == snapshot2

    def test_different_date_not_equal(self):
        """Snapshots with different dates should not be equal."""
        snapshot1 = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )
        snapshot2 = IndicatorSnapshot(
            date=date(2024, 1, 16),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )

        assert snapshot1 != snapshot2

    def test_different_sma_not_equal(self):
        """Snapshots with different SMA should not be equal."""
        snapshot1 = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )
        snapshot2 = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("101"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )

        assert snapshot1 != snapshot2

    def test_hashable_for_use_in_sets(self):
        """Snapshots should be hashable (can be used in sets)."""
        snapshot1 = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )
        snapshot2 = IndicatorSnapshot(
            date=date(2024, 1, 15),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )
        snapshot3 = IndicatorSnapshot(
            date=date(2024, 1, 16),
            sma=Decimal("100"),
            ema=Decimal("100"),
            rsi=Decimal("50"),
        )

        snapshot_set = {snapshot1, snapshot2, snapshot3}
        assert len(snapshot_set) == 2  # snapshot1 and snapshot2 are equal
