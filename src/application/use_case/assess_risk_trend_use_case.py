"""Risk trend evaluation over recent trading days.

Layer: Application
Depends on: AggregateIndicatorsUseCase, IndicatorEvaluator
"""

from datetime import date
from typing import TYPE_CHECKING

from src.application.dto.assess_risk import AssessRiskRequest, AssessRiskTrendResponse
from src.application.use_case.aggregate_indicators_use_case import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.domain.ports.market_data_repository import MarketDataRepository

if TYPE_CHECKING:
    from src.application.services.indicator_evaluator import IndicatorEvaluator

_RANK = {"BULLISH": 0, "NEUTRAL": 1, "BEARISH": 2}


class AssessRiskTrendUseCase:
    """Evaluates risk level trend over the last N trading days."""

    def __init__(
        self,
        repository: MarketDataRepository,
        indicator_evaluator: "IndicatorEvaluator | None",
        indicator_history_days: int,
    ) -> None:
        self._repository = repository
        self._indicator_evaluator = indicator_evaluator
        self._indicator_history_days = indicator_history_days

    def execute(self, request: AssessRiskRequest, days: int = 7) -> AssessRiskTrendResponse:
        """
        Assess risk level trend over the last N trading days.

        Re-uses AggregateIndicatorsUseCase snapshots (no extra DB queries).

        Args:
            request: Standard risk request
            days: Number of recent snapshots to include in history

        Returns:
            AssessRiskTrendResponse with per-day history and direction
        """
        agg_use_case = AggregateIndicatorsUseCase(self._repository)
        agg_response = agg_use_case.execute(
            AggregateIndicatorsRequest(
                ticker=request.ticker,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
                days=self._indicator_history_days,
            )
        )

        if not agg_response.has_values:
            ticker_upper = request.ticker.upper()
            raise ValueError(
                f"Insufficient data for {ticker_upper}. Run "
                f"'saham fetch market {ticker_upper} --days "
                f"{self._indicator_history_days}' first."
            )

        window = agg_response.snapshots[-days:]

        history: list[tuple[date, str, int]] = []
        if self._indicator_evaluator is not None:
            for snapshot in window:
                ctx = self._indicator_evaluator.evaluate(snapshot)
                history.append((snapshot.date, ctx.overall.value.upper(), ctx.confidence))
        else:
            for snapshot in window:
                history.append((snapshot.date, "UNKNOWN", 0))

        # Determine direction: compare first vs last indicator reading
        first_rank = _RANK.get(history[0][1], 1) if history else 1
        last_rank = _RANK.get(history[-1][1], 1) if history else 1

        if last_rank < first_rank:
            direction = "IMPROVING"
        elif last_rank > first_rank:
            direction = "DETERIORATING"
        else:
            direction = "STABLE"

        # Count consecutive days at current level
        current_level = history[-1][1] if history else ""
        days_in_current = 0
        for _, level, _ in reversed(history):
            if level == current_level:
                days_in_current += 1
            else:
                break

        return AssessRiskTrendResponse(
            ticker=agg_response.ticker,
            history=history,
            direction=direction,
            days_in_current=days_in_current,
        )
