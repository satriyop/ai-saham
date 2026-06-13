"""
IndicatorSnapshot value object.

Represents a single point-in-time snapshot of technical indicators for a ticker.
This is a pure domain concept - no behavior, just immutable data.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Union


@dataclass(frozen=True)
class IndicatorSnapshot:
    """
    Single point-in-time snapshot of all indicators for a ticker.

    This value object captures the state of SMA, EMA, and RSI at a specific date.
    It is immutable (frozen) and defined by its attributes.

    The `extras` field allows storing additional indicator values computed
    with custom periods (e.g., fast_ema=EMA(9), slow_ema=EMA(21)), or
    non-numeric contextual data (like sentiment catalyst).

    Attributes:
        date: The date this snapshot represents
        sma: Simple Moving Average value (default period, typically 20)
        ema: Exponential Moving Average value (default period, typically 20)
        rsi: Relative Strength Index value (0-100, default period typically 14)
        extras: Tuple of (name, value) pairs for custom indicator instances
    """

    date: date
    sma: Decimal
    ema: Decimal
    rsi: Decimal
    extras: tuple[tuple[str, Union[Decimal, str]], ...] = ()

    def get(self, name: str) -> Union[Decimal, str]:
        """Get indicator value by name.

        Supports both built-in indicators and custom extras.
        Lookups are case-insensitive for flexibility.

        Built-in names:
        - "RSI" / "rsi" -> self.rsi
        - "SMA" / "sma" -> self.sma
        - "EMA" / "ema" -> self.ema

        Custom names are looked up in the extras field (case-insensitive).

        Args:
            name: Indicator name to retrieve

        Returns:
            The indicator value as Decimal or str

        Raises:
            KeyError: If indicator name is not found
        """
        name_upper = name.upper()

        # Check built-in indicators first (case-insensitive)
        builtin_map = {
            "RSI": self.rsi,
            "SMA": self.sma,
            "EMA": self.ema,
        }
        if name_upper in builtin_map:
            return builtin_map[name_upper]

        # Check extras (case-insensitive)
        for extra_name, extra_value in self.extras:
            if extra_name.upper() == name_upper:
                return extra_value

        # Not found
        available = list(builtin_map.keys()) + [n for n, _ in self.extras]
        raise KeyError(
            f"Indicator '{name}' not found. "
            f"Available: {available}"
        )

    def with_extras(
        self, extras: tuple[tuple[str, Union[Decimal, str]], ...]
    ) -> "IndicatorSnapshot":
        """Create a new snapshot with additional extras.

        This is useful when you need to add custom indicator values
        to an existing snapshot.

        Args:
            extras: Additional (name, value) pairs to add

        Returns:
            New IndicatorSnapshot with combined extras
        """
        combined_extras = self.extras + extras
        return IndicatorSnapshot(
            date=self.date,
            sma=self.sma,
            ema=self.ema,
            rsi=self.rsi,
            extras=combined_extras,
        )
