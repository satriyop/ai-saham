"""
Aggressive risk profile rule set.

Implements the most sensitive evaluation logic with wider thresholds.
Either RSI or trend indicator alone can trigger a signal.

Layer: Domain
"""

from decimal import Decimal

from src.domain.rules.base_rule import BaseRule
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel


class AggressiveRuleSet(BaseRule):
    """
    Aggressive risk evaluation rules.

    Thresholds:
        - RSI > 60: High-risk condition (overbought)
        - RSI < 40: Low-risk condition (oversold)
        - EMA/SMA divergence >= 0.1%: Significant trend

    Logic:
        - Either indicator alone can signal
        - RSI takes priority when it signals
        - Trend used when RSI is neutral
        - Most sensitive to market conditions
    """

    RSI_HIGH_RISK = Decimal("60")
    RSI_LOW_RISK = Decimal("40")
    DIVERGENCE_THRESHOLD = Decimal("0.1")

    @property
    def profile_name(self) -> str:
        return "aggressive"

    def evaluate(self, snapshot: IndicatorSnapshot) -> tuple[RiskLevel, int, list[str]]:
        """
        Evaluate snapshot using aggressive thresholds.

        Either indicator alone can signal. RSI has priority.
        """
        rationale: list[str] = []
        rsi = snapshot.rsi
        magnitude = self._calculate_divergence_magnitude(snapshot)
        direction = self._get_trend_direction(snapshot)

        # Evaluate RSI condition
        rsi_signals_high = rsi > self.RSI_HIGH_RISK
        rsi_signals_low = rsi < self.RSI_LOW_RISK

        # Evaluate trend condition (with threshold check)
        trend_significant = magnitude >= self.DIVERGENCE_THRESHOLD
        trend_down = direction == -1 and trend_significant
        trend_up = direction == 1 and trend_significant

        # Build rationale for RSI
        if rsi_signals_high:
            rationale.append(
                f"RSI {self._format_decimal(rsi)} > "
                f"Aggressive high-risk threshold ({self.RSI_HIGH_RISK})"
            )
        elif rsi_signals_low:
            rationale.append(
                f"RSI {self._format_decimal(rsi)} < "
                f"Aggressive low-risk threshold ({self.RSI_LOW_RISK})"
            )
        else:
            rationale.append(
                f"RSI {self._format_decimal(rsi)} within neutral range "
                f"({self.RSI_LOW_RISK}-{self.RSI_HIGH_RISK})"
            )

        # Build rationale for trend
        if trend_down:
            rationale.append(
                f"EMA < SMA by {self._format_decimal(magnitude)}% "
                f"(downtrend, magnitude >= {self.DIVERGENCE_THRESHOLD}% threshold)"
            )
        elif trend_up:
            rationale.append(
                f"EMA > SMA by {self._format_decimal(magnitude)}% "
                f"(uptrend, magnitude >= {self.DIVERGENCE_THRESHOLD}% threshold)"
            )
        else:
            if magnitude < self.DIVERGENCE_THRESHOLD:
                rationale.append(
                    f"EMA/SMA divergence {self._format_decimal(magnitude)}% < "
                    f"{self.DIVERGENCE_THRESHOLD}% threshold (sideways)"
                )
            else:
                rationale.append(f"EMA/SMA divergence {self._format_decimal(magnitude)}% (neutral)")

        # Count active signals for confidence
        rsi_active = 1 if (rsi_signals_high or rsi_signals_low) else 0
        trend_active = 1 if (trend_up or trend_down) else 0
        rsi_active + trend_active

        # Determine risk level - either indicator can trigger
        # RSI takes priority, then trend
        if rsi_signals_high:
            risk_level = RiskLevel.HIGH_RISK
            if trend_down:
                confidence = 100
                rationale.append("Both indicators confirm HIGH_RISK")
            elif trend_up:
                confidence = 50
                rationale.append("RSI signals HIGH_RISK (trend disagrees)")
            else:
                confidence = 50
                rationale.append("RSI alone signals HIGH_RISK")

        elif rsi_signals_low:
            risk_level = RiskLevel.LOW_RISK
            if trend_up:
                confidence = 100
                rationale.append("Both indicators confirm LOW_RISK")
            elif trend_down:
                confidence = 50
                rationale.append("RSI signals LOW_RISK (trend disagrees)")
            else:
                confidence = 50
                rationale.append("RSI alone signals LOW_RISK")

        elif trend_down:
            # RSI neutral, but trend signals
            risk_level = RiskLevel.HIGH_RISK
            confidence = 50
            rationale.append("Trend alone signals HIGH_RISK (RSI neutral)")

        elif trend_up:
            # RSI neutral, but trend signals
            risk_level = RiskLevel.LOW_RISK
            confidence = 50
            rationale.append("Trend alone signals LOW_RISK (RSI neutral)")

        else:
            # Both neutral
            risk_level = RiskLevel.MODERATE
            confidence = 0
            rationale.append("Both indicators neutral, MODERATE assessment")

        return risk_level, confidence, rationale
