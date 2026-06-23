"""
BandarGate — execution gate for institutional distribution conflict (Rec 5).

In IDX, 'bandar' (institutional operators / big players) accumulation or
distribution heavily determines whether technical breakouts succeed. Retail
traders following technical signals can be caught in a distribution trap where
institutions are quietly selling into retail demand (pump & dump dynamics).

This gate downgrades a LOW_RISK technical assessment to MODERATE when the
5-day bandar flow shows active distribution — preventing entry into a retail
trap even when the RSI and moving averages appear constructive.

Applies only to LOW_RISK technical signals. MODERATE and HIGH_RISK are
already cautious; no downgrade needed.

Layer: Domain
"""

from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate
from src.domain.value_objects.risk_signal import RiskLevel

# Labels from BandarDetectorSnapshot._INTENSITY_SCORE that indicate distribution
_DISTRIBUTION_LABELS = frozenset({
    "Small Dist", "Big Dist",
    "Small Dis", "Big Dis",   # backward-compat aliases
})


class BandarGate(RiskGate):
    """
    Execution gate: bandar 5-day distribution conflicts with LOW_RISK signal.

    Fires only when current_risk is LOW_RISK AND bandar flow is distributing.
    Downgrades the assessment to MODERATE with reduced confidence.
    """

    def evaluate(self, context: GateContext, current_risk: RiskLevel) -> GateResult:
        if current_risk is not RiskLevel.LOW_RISK:
            return GateResult(
                triggered=False,
                override_risk=None,
                reason="not applicable (technical signal is not LOW_RISK)",
                confidence=0,
            )
        if context.five_day_accdist is None:
            return GateResult(
                triggered=False,
                override_risk=None,
                reason="no bandar flow data — gate skipped",
                confidence=0,
            )
        if context.bandar_is_distributing:
            return GateResult(
                triggered=True,
                override_risk=RiskLevel.MODERATE,
                reason=(
                    f"Bandar distribution ({context.five_day_accdist})"
                    " conflicts with LOW_RISK technical signal (retail trap risk)"
                ),
                confidence=50,
            )
        return GateResult(
            triggered=False,
            override_risk=None,
            reason=f"Bandar 5-day ({context.five_day_accdist}) consistent with signal",
            confidence=100,
        )
