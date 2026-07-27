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

from dataclasses import dataclass

from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate

_DEFAULT_MIN_FREE_FLOAT_PCT: float = 15.0  # aligned with MSCI minimum inclusion threshold


@dataclass(frozen=True)
class FreeFloatGatePolicy:
    missing_data_action: str = "skip"
    missing_data_confidence: int = 0
    triggered_confidence: int = 100
    pass_confidence: int = 100


class FreeFloatGate(RiskGate):
    """
    Structural gate: rejects stocks with dangerously thin public float.

    Runs in the structural tier (same tier as FundamentalGate, LiquidityGate).
    """

    def __init__(
        self,
        min_free_float_pct: float = _DEFAULT_MIN_FREE_FLOAT_PCT,
        policy: FreeFloatGatePolicy | None = None,
    ) -> None:
        self._threshold = min_free_float_pct
        self._policy = policy or FreeFloatGatePolicy()

    def evaluate(self, context: GateContext) -> GateResult:
        if context.free_float_pct is None:
            triggered = self._policy.missing_data_action == "block"
            return GateResult(
                triggered=triggered,
                reason=(
                    "Free float data unavailable — gate blocked"
                    if triggered
                    else "Free float data unavailable — gate skipped"
                ),
                confidence=self._policy.missing_data_confidence,
            )

        ff = context.free_float_pct

        if ff < self._threshold:
            return GateResult(
                triggered=True,
                reason=(
                    f"Thin free float: {ff:.1f}% < {self._threshold:.0f}% threshold "
                    f"(index exclusion / forced-selling risk)"
                ),
                confidence=self._policy.triggered_confidence,
            )

        return GateResult(
            triggered=False,
            reason=f"Free float {ff:.1f}% above {self._threshold:.0f}% threshold",
            confidence=self._policy.pass_confidence,
        )
