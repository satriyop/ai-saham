"""
BandarGate — execution gate for institutional distribution conflict (Rec 5).

In IDX, 'bandar' (institutional operators / big players) accumulation or
distribution heavily determines whether technical breakouts succeed. Retail
traders following technical signals can be caught in a distribution trap where
institutions are quietly selling into retail demand (pump & dump dynamics).

This gate fires when the 5-day bandar flow shows active distribution —
preventing entry into a retail trap even when the RSI and moving averages
appear constructive.

Layer: Domain
"""

from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate

# Labels from BandarDetectorSnapshot that indicate distribution
_DISTRIBUTION_LABELS = frozenset({
    "Small Dist", "Big Dist",
    "Small Dis", "Big Dis",   # backward-compat aliases
})


class BandarGate(RiskGate):
    """
    Execution gate: bandar 5-day distribution present.

    Fires unconditionally when distribution is present in the 5-day flow.
    Skips silently when no bandar flow data is available.
    """

    def evaluate(self, context: GateContext) -> GateResult:
        if context.five_day_accdist is None:
            return GateResult(
                triggered=False,
                reason="no bandar flow data — gate skipped",
                confidence=0,
            )
        if context.five_day_accdist in _DISTRIBUTION_LABELS:
            return GateResult(
                triggered=True,
                reason=(
                    f"Bandar distribution ({context.five_day_accdist})"
                    " — distribution trap risk"
                ),
                confidence=80,
            )
        return GateResult(
            triggered=False,
            reason=f"Bandar 5-day ({context.five_day_accdist}) consistent",
            confidence=100,
        )
