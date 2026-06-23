"""
ConfirmIntradayOpenUseCase — convert pre-open candidates into post-open decisions.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.domain.value_objects import tick_size as tick_size_module
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmation,
    IntradayConfirmationCandidate,
    IntradayConfirmationResult,
    IntradayDecision,
)


@dataclass(frozen=True)
class ConfirmIntradayOpenRequest:
    """Request DTO for confirming pre-open candidates after auction clears."""

    candidates: list[IntradayConfirmationCandidate]
    run_date: date | None = None
    max_stop_pct: Decimal = Decimal("0.07")
    # Tick-friction gate (Phase 1.2)
    tick_friction_gate: bool = True
    min_target_ticks: int = 3
    min_stop_ticks: int = 2
    # Regime gate (Phase 1.3)
    regime: str | None = None
    regime_gate_enabled: bool = True
    tighten_in_regimes: tuple[str, ...] = ("WEAK", "RISK_OFF")
    gap_pct_tightening_factor: Decimal = Decimal("0.5")
    require_backed_in_weak: bool = True


class ConfirmIntradayOpenUseCase:
    """Apply deterministic post-open gates to pre-open candidates."""

    def execute(self, request: ConfirmIntradayOpenRequest) -> IntradayConfirmationResult:
        confirmed_date = request.run_date or date.today()
        confirmations = tuple(
            self._confirm_candidate(candidate, request)
            for candidate in request.candidates
        )
        return IntradayConfirmationResult(
            confirmed_date=confirmed_date,
            max_stop_pct=request.max_stop_pct,
            confirmations=confirmations,
        )

    def _confirm_candidate(
        self,
        candidate: IntradayConfirmationCandidate,
        request: ConfirmIntradayOpenRequest,
    ) -> IntradayConfirmation:
        max_stop_pct = request.max_stop_pct
        reasons: list[str] = []

        if candidate.opening_price is None:
            return self._result(
                candidate,
                IntradayDecision.SKIP_INSUFFICIENT_DATA,
                planned_entry=None,
                stop_pct=None,
                reasons=("missing opening price",),
            )

        if (
            candidate.entry_range_low is None
            or candidate.entry_range_high is None
            or candidate.suggested_entry is None
            or candidate.atr_stop is None
        ):
            return self._result(
                candidate,
                IntradayDecision.SKIP_INSUFFICIENT_DATA,
                planned_entry=None,
                stop_pct=None,
                reasons=("missing entry range, suggested entry, or stop",),
            )

        opening = candidate.opening_price

        # Regime gate: in WEAK/RISK_OFF, tighten entry band and require BACKED accumulation
        effective_range_low = candidate.entry_range_low
        effective_range_high = candidate.entry_range_high
        regime_tightening_active = (
            request.regime_gate_enabled
            and request.regime is not None
            and request.regime.upper() in request.tighten_in_regimes
        )
        if regime_tightening_active:
            midpoint = (candidate.entry_range_high + candidate.entry_range_low) / Decimal("2")
            half_band = (candidate.entry_range_high - midpoint) * request.gap_pct_tightening_factor
            effective_range_high = midpoint + half_band
            effective_range_low = midpoint - half_band
            reasons.append(
                f"regime {request.regime}: entry band tightened to"
                f" {effective_range_low:,.0f}–{effective_range_high:,.0f}"
            )
            if request.require_backed_in_weak and candidate.accum_tag not in ("BACKED",):
                return self._result(
                    candidate,
                    IntradayDecision.SKIP_BEARISH_CONTEXT,
                    planned_entry=opening,
                    stop_pct=self._stop_pct(opening, candidate.atr_stop),
                    reasons=tuple(
                        reasons + [
                            f"regime {request.regime}: BACKED accumulation required"
                            f" (got {candidate.accum_tag or 'None'})"
                        ]
                    ),
                )

        if opening > effective_range_high:
            return self._result(
                candidate,
                IntradayDecision.SKIP_GAP_UP,
                planned_entry=opening,
                stop_pct=self._stop_pct(opening, candidate.atr_stop),
                reasons=tuple(
                    reasons + [f"open {opening} above range high {effective_range_high}"]
                ),
            )

        if opening < effective_range_low:
            return self._result(
                candidate,
                IntradayDecision.SKIP_GAP_DOWN,
                planned_entry=opening,
                stop_pct=self._stop_pct(opening, candidate.atr_stop),
                reasons=tuple(
                    reasons + [f"open {opening} below range low {effective_range_low}"]
                ),
            )

        reasons.append("open inside entry range")

        if candidate.trend == "BEARISH":
            return self._result(
                candidate,
                IntradayDecision.SKIP_BEARISH_CONTEXT,
                planned_entry=opening,
                stop_pct=self._stop_pct(opening, candidate.atr_stop),
                reasons=tuple(reasons + ["pre-open trend is BEARISH"]),
            )

        if candidate.accum_tag == "DISTRIBUTING":
            return self._result(
                candidate,
                IntradayDecision.SKIP_BEARISH_CONTEXT,
                planned_entry=opening,
                stop_pct=self._stop_pct(opening, candidate.atr_stop),
                reasons=tuple(reasons + ["broker context is DISTRIBUTING"]),
            )

        stop_pct = self._stop_pct(opening, candidate.atr_stop)
        if stop_pct is None:
            return self._result(
                candidate,
                IntradayDecision.SKIP_INSUFFICIENT_DATA,
                planned_entry=opening,
                stop_pct=None,
                reasons=tuple(reasons + ["invalid stop price"]),
            )

        if stop_pct > max_stop_pct * Decimal("100"):
            return self._result(
                candidate,
                IntradayDecision.SKIP_RISK_TOO_WIDE,
                planned_entry=opening,
                stop_pct=stop_pct,
                reasons=tuple(
                    reasons
                    + [f"stop {stop_pct:.1f}% exceeds max {max_stop_pct * 100:.1f}%"]
                ),
            )

        reasons.append(f"stop {stop_pct:.1f}% within max {max_stop_pct * 100:.1f}%")

        # Tick-friction gate: target and stop must cover minimum ticks (IDX round-trip cost).
        # IDX actual round-trip: ~0.41% (Stockbit) to ~0.65% (IPOT) incl. 0.10% PPh on sell.
        if request.tick_friction_gate and candidate.atr_stop is not None:
            atr_distance = opening - candidate.atr_stop
            implied_target = opening + atr_distance  # symmetric 1:1 projection
            stop_ticks = tick_size_module.ticks_between(candidate.atr_stop, opening)
            target_ticks = tick_size_module.ticks_between(opening, implied_target)
            if stop_ticks < request.min_stop_ticks or target_ticks < request.min_target_ticks:
                return self._result(
                    candidate,
                    IntradayDecision.SKIP_LOW_VOLATILITY,
                    planned_entry=opening,
                    stop_pct=stop_pct,
                    reasons=tuple(
                        reasons + [
                            f"tick-friction: stop={stop_ticks}t target={target_ticks}t"
                            f" (min stop={request.min_stop_ticks}t"
                            f" target={request.min_target_ticks}t)"
                        ]
                    ),
                )

        if candidate.trend == "BULLISH":
            decision = IntradayDecision.ENTER
            reasons.append("pre-open trend is BULLISH")
        else:
            decision = IntradayDecision.WAIT
            reasons.append("pre-open trend is not bullish")

        return self._result(
            candidate,
            decision,
            planned_entry=opening,
            stop_pct=stop_pct,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _stop_pct(entry: Decimal, stop: Decimal | None) -> Decimal | None:
        if stop is None or entry <= 0 or stop <= 0 or stop >= entry:
            return None
        return ((entry - stop) / entry * Decimal("100")).quantize(Decimal("0.1"))

    @staticmethod
    def _result(
        candidate: IntradayConfirmationCandidate,
        decision: IntradayDecision,
        planned_entry: Decimal | None,
        stop_pct: Decimal | None,
        reasons: tuple[str, ...],
    ) -> IntradayConfirmation:
        return IntradayConfirmation(
            ticker=candidate.ticker,
            decision=decision,
            opening_price=candidate.opening_price,
            planned_entry=planned_entry,
            stop_loss_price=candidate.atr_stop,
            stop_pct=stop_pct,
            reasons=reasons,
            iev=candidate.iev,
            trend=candidate.trend,
            rsi=candidate.rsi,
            gap_pct=candidate.gap_pct,
            accum_tag=candidate.accum_tag,
            fvwap_discount_pct=candidate.fvwap_discount_pct,
            opening_price_source=candidate.opening_price_source,
            opening_price_confidence=candidate.opening_price_confidence,
            opening_price_timestamp=candidate.opening_price_timestamp,
            auto_confirmed=candidate.auto_confirmed,
            manual_override=candidate.manual_override,
        )
