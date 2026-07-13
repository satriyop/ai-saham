"""
Indicator type and definition schema for the custom rules DSL.

Layer: Application
"""

from dataclasses import dataclass
from enum import Enum
from typing import Union


class IndicatorType(Enum):
    """Supported technical indicator types for parameterized definitions.

    Defines which indicator calculations are supported. Users define
    indicator instances using these types with custom periods.

    Example YAML:
        indicators:
          fast_ema:
            type: EMA      # IndicatorType.EMA
            period: 9
    """

    RSI = "RSI"
    SMA = "SMA"
    EMA = "EMA"
    SENTIMENT_SCORE = "SENTIMENT_SCORE"
    SENTIMENT_LABEL = "SENTIMENT_LABEL"
    SENTIMENT_CATALYST = "SENTIMENT_CATALYST"

    @classmethod
    def from_string(cls, value: str) -> "IndicatorType":
        """Create IndicatorType from string value.

        Args:
            value: Type name (case-insensitive)

        Returns:
            Matching IndicatorType enum

        Raises:
            ValueError: If value doesn't match any type
        """
        normalized = value.upper().strip()
        for ind_type in cls:
            if ind_type.value == normalized:
                return ind_type
        valid = [t.value for t in cls]
        raise ValueError(f"Unknown indicator type '{value}'. Must be one of: {valid}")


# Built-in indicator names (available without explicit definition)
# These use default periods if referenced without definition
BUILTIN_INDICATORS: dict[str, tuple["IndicatorType", int]] = {
    "RSI": (IndicatorType.RSI, 14),
    "SMA": (IndicatorType.SMA, 20),
    "EMA": (IndicatorType.EMA, 20),
    "SENTIMENT_SCORE": (IndicatorType.SENTIMENT_SCORE, 0),
    "SENTIMENT_LABEL": (IndicatorType.SENTIMENT_LABEL, 0),
    "SENTIMENT_CATALYST": (IndicatorType.SENTIMENT_CATALYST, 0),
}


# Backward compatibility alias
Indicator = IndicatorType


@dataclass(frozen=True)
class IndicatorDefinition:
    """Definition of a named indicator instance.

    Supports two modes:
    1. Type-based: Standard indicator with type and period (e.g., EMA with period 9)
    2. Formula-based: Composite indicator defined by formula expression

    Example (type-based):
        IndicatorDefinition(name="fast_ema", indicator_type=IndicatorType.EMA, period=9)
        IndicatorDefinition(name="atr_14", indicator_type="ATR", period=14)  # Plugin

    Example (formula-based):
        IndicatorDefinition(name="smooth_rsi", formula="SMA(RSI(14), 10)")
        IndicatorDefinition(name="macd_line", formula="EMA(CLOSE, 12) - EMA(CLOSE, 26)")

    Attributes:
        name: Unique name for this indicator instance (e.g., "fast_ema")
        indicator_type: Type of indicator calculation. Can be:
            - IndicatorType enum for built-ins (RSI, SMA, EMA)
            - str for plugin indicators (e.g., "ATR", "VWAP")
            - None for formula-based indicators
        period: Lookback period for the calculation (>= 1), None for formulas
        formula: Formula expression string (e.g., "SMA(RSI(14), 10)"), None for type-based
        override: If True, allows shadowing built-in indicator names
    """

    name: str
    indicator_type: Union[IndicatorType, str, None] = None
    period: int | None = None
    formula: str | None = None
    override: bool = False

    def __post_init__(self) -> None:
        """Validate indicator definition fields."""
        if not self.name:
            raise ValueError("Indicator name cannot be empty")

        has_type = self.indicator_type is not None
        has_formula = self.formula is not None

        # Must have exactly one: (type + period) OR formula
        if has_type and has_formula:
            raise ValueError(
                f"Indicator '{self.name}' cannot have both 'type' and 'formula'. "
                "Use either type+period OR formula."
            )

        if not has_type and not has_formula:
            raise ValueError(
                f"Indicator '{self.name}' must have either 'type' (with period) "
                "or 'formula'."
            )

        # Type-based validation
        if has_type:
            if self.period is None:
                raise ValueError(
                    f"Indicator '{self.name}' with type requires a period."
                )
            if self.period < 1:
                raise ValueError(
                    f"Indicator period must be >= 1, got {self.period}"
                )

        # Formula-based validation
        if has_formula:
            if self.period is not None:
                raise ValueError(
                    f"Formula indicator '{self.name}' should not have a period. "
                    "Period is determined by the formula expression."
                )
            if not self.formula.strip():
                raise ValueError(
                    f"Indicator '{self.name}' has empty formula."
                )

    def is_formula(self) -> bool:
        """Check if this is a formula-based indicator.

        Returns:
            True if indicator is defined by a formula expression.
        """
        return self.formula is not None

    def get_type_name(self) -> str:
        """Get indicator type as string (works for both enum and plugin types).

        Returns:
            Uppercase type name (e.g., "RSI", "ATR") or "FORMULA" for formulas.
        """
        if self.is_formula():
            return "FORMULA"
        if isinstance(self.indicator_type, IndicatorType):
            return self.indicator_type.value
        return str(self.indicator_type).upper()
