"""
Balanced risk profile rule set.

Implements moderate evaluation logic with standard thresholds.
Uses majority rules - either indicator can trigger a signal,
but conflicting signals result in MODERATE.

Layer: Domain
"""

from decimal import Decimal

from src.domain.rules.base_rule import BaseRule
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel


class BalancedRuleSet(BaseRule):
    """
    Balanced risk evaluation rules.

    Thresholds:
        - RSI > 70: High-risk condition (overbought)
        - RSI < 30: Low-risk condition (oversold)
        - Any EMA/SMA divergence counts (no minimum threshold)

    Logic:
        - Majority rules: either indicator can signal
        - If both agree -> strong signal with 100% confidence
        - If one signals, other neutral -> signal with 50% confidence
        - If signals conflict -> MODERATE with 50% confidence
        - If both neutral -> MODERATE with 0% confidence
    """

    RSI_HIGH_RISK = Decimal("70")
    RSI_LOW_RISK = Decimal("30")
    DIVERGENCE_THRESHOLD = Decimal("0")  # Any divergence counts

    @property
    def profile_name(self) -> str:
        return "balanced"

    def evaluate(self, snapshot: IndicatorSnapshot) -> tuple[RiskLevel, int, list[str]]:
        """
        Evaluate snapshot using balanced thresholds.

        Majority rules - either indicator can signal.
        """
        rationale: list[str] = []
        rsi = snapshot.rsi
        magnitude = self._calculate_divergence_magnitude(snapshot)
        direction = self._get_trend_direction(snapshot)

        # Evaluate RSI: -1 (low-risk), 0 (neutral), 1 (high-risk)
        if rsi > self.RSI_HIGH_RISK:
            rsi_signal = 1
            rationale.append(
                f"RSI {self._format_decimal(rsi)} > "
                f"Balanced high-risk threshold ({self.RSI_HIGH_RISK})"
            )
        elif rsi < self.RSI_LOW_RISK:
            rsi_signal = -1
            rationale.append(
                f"RSI {self._format_decimal(rsi)} < "
                f"Balanced low-risk threshold ({self.RSI_LOW_RISK})"
            )
        else:
            rsi_signal = 0
            rationale.append(
                f"RSI {self._format_decimal(rsi)} within neutral range "
                f"({self.RSI_LOW_RISK}-{self.RSI_HIGH_RISK})"
            )

        # Evaluate trend: -1 (downtrend/high-risk), 0 (neutral), 1 (uptrend/low-risk)
        # Note: uptrend (EMA > SMA) is LOW_RISK, downtrend is HIGH_RISK
        if direction == 1:  # Uptrend
            trend_signal = -1  # Low-risk direction
            rationale.append(f"EMA > SMA by {self._format_decimal(magnitude)}% (uptrend)")
        elif direction == -1:  # Downtrend
            trend_signal = 1  # High-risk direction
            rationale.append(f"EMA < SMA by {self._format_decimal(magnitude)}% (downtrend)")
        else:  # Sideways
            trend_signal = 0
            rationale.append(f"EMA/SMA divergence {self._format_decimal(magnitude)}% (sideways)")

        # Combine signals using majority rules
        # Convert trend_signal to match risk direction: positive = high-risk, negative = low-risk
        combined = rsi_signal + trend_signal

        # Count active signals for confidence
        active_signals = (1 if rsi_signal != 0 else 0) + (1 if trend_signal != 0 else 0)

        if combined > 0:
            # Net high-risk signal
            risk_level = RiskLevel.HIGH_RISK
            if rsi_signal == 1 and trend_signal == 1:
                confidence = 100
                rationale.append("Both indicators confirm HIGH_RISK")
            else:
                confidence = 50
                rationale.append("Net signal indicates HIGH_RISK")

        elif combined < 0:
            # Net low-risk signal
            risk_level = RiskLevel.LOW_RISK
            if rsi_signal == -1 and trend_signal == -1:
                confidence = 100
                rationale.append("Both indicators confirm LOW_RISK")
            else:
                confidence = 50
                rationale.append("Net signal indicates LOW_RISK")

        else:
            # Signals cancel out or both neutral
            risk_level = RiskLevel.MODERATE
            if active_signals == 0:
                confidence = 0
                rationale.append("Both indicators neutral, MODERATE assessment")
            else:
                confidence = 50
                rationale.append("Signals conflict, Balanced profile returns MODERATE")

        return risk_level, confidence, rationale
