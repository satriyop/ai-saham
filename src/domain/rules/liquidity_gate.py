"""
LiquidityGate — structural gate for illiquid and small-cap stocks (Rec 2 + Rec 6).

Two complementary checks implemented as one gate (checked in order):

  Rec 6 — Market cap tiering:
    Sub-IDR-1T stocks (third-liner) face chronic manipulation risk, wide
    bid-ask spreads, and forced liquidation spirals. Even a technically
    clean signal cannot overcome thin-float dynamics in Indonesia's illiquid
    market segments. If market cap is below the threshold, fire immediately.

  Rec 2 — Median 20-day transaction value:
    A stock's daily trading value (price × volume) determines whether a
    position can be entered and exited without material slippage. Even if
    market cap is large, a stock that has recently gone illiquid (e.g.,
    halted trading or sector rout) should be flagged HIGH_RISK.
    IDR 5B/day is the minimum threshold for swing-tradeable liquidity.

Both conditions produce a HIGH_RISK override.

Layer: Domain
"""

import statistics
from dataclasses import dataclass

from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate

_THIRD_LINER_CAP_IDR = 1_000_000_000_000  # IDR 1T
_LIQUIDITY_FLOOR_IDR = 5_000_000_000  # IDR 5B per day
_DEFAULT_LOOKBACK = 20  # trading sessions

# Non-triggering reason, keyed by (market-cap leg checked, median-tx leg checked).
# (False, False) never reaches here — that case is GateOutcome.UNEVALUABLE.
_PASS_REASONS = {
    (True, True): "liquidity and market cap checks passed",
    (True, False): "market cap above floor; no traded sessions (median tx floor not applied)",
    (False, True): "median 20d tx above floor; market cap unknown (cap floor not applied)",
}


@dataclass(frozen=True)
class LiquidityGatePolicy:
    missing_data_action: str = "skip"
    missing_data_confidence: int = 0
    triggered_confidence: int = 100
    pass_confidence: int = 100


class LiquidityGate(RiskGate):
    """
    Structural gate: sub-IDR-1T market cap or low 20-day median transaction value.

    Market cap check (static, requires fundamentals data) runs before median
    transaction check (dynamic, requires recent candles). Either condition
    alone triggers HIGH_RISK. If neither leg has usable input the result is
    ``GateOutcome.UNEVALUABLE``; whether that also blocks is governed by
    ``LiquidityGatePolicy.missing_data_action``. If exactly one leg has input,
    the gate reaches a verdict on that leg and the reason names the leg that
    was not applied.
    """

    def __init__(
        self,
        third_liner_cap_idr: int = _THIRD_LINER_CAP_IDR,
        liquidity_floor_idr: int = _LIQUIDITY_FLOOR_IDR,
        lookback_days: int = _DEFAULT_LOOKBACK,
        policy: LiquidityGatePolicy | None = None,
    ) -> None:
        self._cap_threshold = third_liner_cap_idr
        self._liquidity_floor = liquidity_floor_idr
        self._lookback = lookback_days
        self._policy = policy or LiquidityGatePolicy()

    def evaluate(self, context: GateContext) -> GateResult:
        # Rec 6: market cap tiering (static check, runs first)
        cap_checked = context.market_cap_idr is not None
        if context.market_cap_idr is not None:
            if context.market_cap_idr < self._cap_threshold:
                cap_b = context.market_cap_idr // 1_000_000_000
                threshold_t = self._cap_threshold // 1_000_000_000_000
                return GateResult(
                    triggered=True,
                    reason=(
                        f"Third-liner: market cap {cap_b}B IDR"
                        f" < {threshold_t}T IDR threshold (manipulation/spread risk)"
                    ),
                    confidence=self._policy.triggered_confidence,
                )

        # Rec 2: median 20-day transaction value (dynamic, requires candles)
        tx_checked = False
        if context.recent_candles:
            candles = context.recent_candles[-self._lookback :]
            tx_values = [float(c.close * c.volume) for c in candles if c.volume > 0]
            if tx_values:
                tx_checked = True
                median_tx = statistics.median(tx_values)
                if median_tx < self._liquidity_floor:
                    median_m = int(median_tx) // 1_000_000
                    floor_b = self._liquidity_floor // 1_000_000_000
                    return GateResult(
                        triggered=True,
                        reason=(
                            f"Illiquid: median 20d tx {median_m}M IDR"
                            f" < {floor_b}B IDR/day floor (slippage risk)"
                        ),
                        confidence=self._policy.triggered_confidence,
                    )

        if not cap_checked and not tx_checked:
            blocks = self._policy.missing_data_action == "block"
            return GateResult.unevaluable(
                reason=(
                    "liquidity data unavailable — gate blocked"
                    if blocks
                    else "liquidity data unavailable — gate skipped"
                ),
                confidence=self._policy.missing_data_confidence,
                blocks=blocks,
            )

        # At least one leg reached a verdict and nothing fired, so this is a
        # PASS. When the other leg had no usable input the reason names it
        # rather than claiming both checks passed; the missing input itself is
        # recorded in GateContextCompleteness.missingness.
        return GateResult(
            triggered=False,
            reason=_PASS_REASONS[(cap_checked, tx_checked)],
            confidence=self._policy.pass_confidence,
        )
