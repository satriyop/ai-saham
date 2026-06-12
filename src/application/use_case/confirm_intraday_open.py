"""
ConfirmIntradayOpenUseCase — convert pre-open candidates into post-open decisions.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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


class ConfirmIntradayOpenUseCase:
    """Apply deterministic post-open gates to pre-open candidates."""

    def execute(self, request: ConfirmIntradayOpenRequest) -> IntradayConfirmationResult:
        confirmed_date = request.run_date or date.today()
        confirmations = tuple(
            self._confirm_candidate(candidate, request.max_stop_pct)
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
        max_stop_pct: Decimal,
    ) -> IntradayConfirmation:
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
        if opening > candidate.entry_range_high:
            return self._result(
                candidate,
                IntradayDecision.SKIP_GAP_UP,
                planned_entry=opening,
                stop_pct=self._stop_pct(opening, candidate.atr_stop),
                reasons=(
                    f"open {opening} above range high {candidate.entry_range_high}",
                ),
            )

        if opening < candidate.entry_range_low:
            return self._result(
                candidate,
                IntradayDecision.SKIP_GAP_DOWN,
                planned_entry=opening,
                stop_pct=self._stop_pct(opening, candidate.atr_stop),
                reasons=(
                    f"open {opening} below range low {candidate.entry_range_low}",
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
        )
