"""
Conservative risk profile rule set.

Implements the most cautious evaluation logic with strict thresholds.
Requires BOTH RSI and trend indicators to agree before signaling
HIGH_RISK or LOW_RISK.

Layer: Domain
"""

from decimal import Decimal

from src.domain.rules.base_rule import BaseRule
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel


class ConservativeRuleSet(BaseRule):
    """
    Conservative risk evaluation rules.

    Thresholds:
        - RSI > 75: High-risk condition (overbought)
        - RSI < 25: Low-risk condition (oversold)
        - EMA/SMA divergence >= 1%: Significant trend

    Logic:
        - Requires BOTH indicators to agree for non-MODERATE signal
        - If RSI signals high-risk AND trend confirms (downtrend), signal HIGH_RISK
        - If RSI signals low-risk AND trend confirms (uptrend), signal LOW_RISK
        - Otherwise, signal MODERATE
    """

    RSI_HIGH_RISK = Decimal("75")
    RSI_LOW_RISK = Decimal("25")
    DIVERGENCE_THRESHOLD = Decimal("1.0")

    @property
    def profile_name(self) -> str:
        return "conservative"

    def evaluate(
        self, snapshot: IndicatorSnapshot
    ) -> tuple[RiskLevel, int, list[str]]:
        """
        Evaluate snapshot using conservative thresholds.

        Both RSI and trend must agree for HIGH_RISK or LOW_RISK.
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
                f"Conservative high-risk threshold ({self.RSI_HIGH_RISK})"
            )
        elif rsi_signals_low:
            rationale.append(
                f"RSI {self._format_decimal(rsi)} < "
                f"Conservative low-risk threshold ({self.RSI_LOW_RISK})"
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
                rationale.append(
                    f"EMA/SMA divergence {self._format_decimal(magnitude)}% (neutral)"
                )

        # Calculate confidence and determine risk level
        # Conservative requires BOTH indicators to agree
        rules_satisfied = 0

        # HIGH_RISK: RSI overbought AND downtrend
        if rsi_signals_high and trend_down:
            rules_satisfied = 2
            risk_level = RiskLevel.HIGH_RISK
            rationale.append("Both indicators confirm HIGH_RISK (RSI overbought + downtrend)")

        # LOW_RISK: RSI oversold AND uptrend
        elif rsi_signals_low and trend_up:
            rules_satisfied = 2
            risk_level = RiskLevel.LOW_RISK
            rationale.append("Both indicators confirm LOW_RISK (RSI oversold + uptrend)")

        # Mixed signals or neutral - default to MODERATE
        else:
            # Count how many indicators are signaling (for confidence)
            if rsi_signals_high or rsi_signals_low:
                rules_satisfied += 1
            if trend_up or trend_down:
                rules_satisfied += 1

            risk_level = RiskLevel.MODERATE

            if rules_satisfied == 0:
                rationale.append("Both indicators neutral, MODERATE assessment")
            else:
                rationale.append(
                    "Indicators do not agree, Conservative profile defaults to MODERATE"
                )

        confidence = (rules_satisfied * 100) // 2  # 0, 50, or 100

        return risk_level, confidence, rationale
