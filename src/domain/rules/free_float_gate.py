"""
FreeFloatGate — structural gate for thin free-float risk (Rec 7).

Fires when free float (individual_pct + institution_pct from IDX shareholding
disclosure) falls below threshold. The MSCI minimum inclusion threshold is 15%;
stocks below this face index exclusion and forced institutional selling.

Note: institution_pct aggregates all institutional categories and may include
some strategic holders beyond the primary controlling stake. True free float
may be somewhat lower for heavily state-linked stocks. This is the best
estimate available from the shareholding_composition schema.

Layer: Domain
"""

from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate
from src.domain.value_objects.risk_signal import RiskLevel

_DEFAULT_MIN_FREE_FLOAT_PCT: float = 15.0  # aligned with MSCI minimum inclusion threshold


class FreeFloatGate(RiskGate):
    """
    Structural gate: rejects stocks with dangerously thin public float.

    Runs before the technical rule engine (same tier as FundamentalGate,
    LiquidityGate). Fires regardless of current_risk.
    """

    def __init__(self, min_free_float_pct: float = _DEFAULT_MIN_FREE_FLOAT_PCT) -> None:
        self._threshold = min_free_float_pct

    def evaluate(self, context: GateContext, current_risk: RiskLevel) -> GateResult:
        if context.free_float_pct is None:
            return GateResult(
                triggered=False,
                override_risk=None,
                reason="Free float data unavailable — gate skipped",
                confidence=0,
            )

        ff = context.free_float_pct

        if ff < self._threshold:
            return GateResult(
                triggered=True,
                override_risk=RiskLevel.HIGH_RISK,
                reason=(
                    f"Thin free float: {ff:.1f}% < {self._threshold:.0f}% threshold "
                    f"(index exclusion / forced-selling risk)"
                ),
                confidence=100,
            )

        return GateResult(
            triggered=False,
            override_risk=None,
            reason=f"Free float {ff:.1f}% above {self._threshold:.0f}% threshold",
            confidence=100,
        )
