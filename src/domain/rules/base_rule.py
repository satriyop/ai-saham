"""
Base rule interface for risk profile evaluation.

Defines the contract that all risk profile rule sets must implement.
Provides common utility methods for indicator analysis.

Layer: Domain
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel


class BaseRule(ABC):
    """
    Abstract base class for risk profile rule evaluation.

    Each risk profile (Conservative, Balanced, Aggressive) implements
    this interface with its own thresholds and evaluation logic.

    Subclasses must implement:
        - profile_name: String identifier for the profile
        - evaluate(): Core evaluation logic returning risk level, confidence, rationale
    """

    @property
    @abstractmethod
    def profile_name(self) -> str:
        """Return the profile name (e.g., 'conservative')."""
        ...

    @abstractmethod
    def evaluate(
        self, snapshot: IndicatorSnapshot
    ) -> tuple[RiskLevel, int, list[str]]:
        """
        Evaluate an indicator snapshot against this profile's rules.

        Args:
            snapshot: IndicatorSnapshot containing SMA, EMA, RSI values

        Returns:
            Tuple of:
                - RiskLevel: The determined risk level
                - int: Confidence score (0, 50, or 100)
                - list[str]: Human-readable rationale explaining the assessment
        """
        ...

    def _calculate_divergence_magnitude(self, snapshot: IndicatorSnapshot) -> Decimal:
        """
        Calculate EMA/SMA divergence magnitude as absolute percentage.

        Formula: |EMA - SMA| / SMA * 100

        Args:
            snapshot: IndicatorSnapshot with SMA and EMA values

        Returns:
            Absolute percentage divergence (e.g., Decimal("1.5") for 1.5%)
            Returns Decimal("0") if SMA is zero to avoid division by zero
        """
        if snapshot.sma == 0:
            return Decimal("0")
        return abs(snapshot.ema - snapshot.sma) / snapshot.sma * 100

    def _get_trend_direction(self, snapshot: IndicatorSnapshot) -> int:
        """
        Determine trend direction from EMA vs SMA relationship.

        Args:
            snapshot: IndicatorSnapshot with SMA and EMA values

        Returns:
            1: Uptrend (EMA > SMA) -> indicates LOW_RISK tendency
            -1: Downtrend (EMA < SMA) -> indicates HIGH_RISK tendency
            0: Sideways (EMA == SMA) -> indicates MODERATE tendency
        """
        diff = snapshot.ema - snapshot.sma
        if diff > 0:
            return 1  # Uptrend
        elif diff < 0:
            return -1  # Downtrend
        return 0  # Sideways

    def _format_decimal(self, value: Decimal, decimals: int = 2) -> str:
        """Format Decimal for display in rationale."""
        return f"{value:.{decimals}f}"
