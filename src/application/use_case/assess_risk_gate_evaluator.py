"""Configured risk gate evaluation path for risk assessment.

Layer: Application
Depends on: Domain rules, Domain value objects, AggregateIndicatorsUseCase
"""

from dataclasses import replace
from datetime import date

from src.application.dto.assess_risk import AssessRiskRequest, AssessRiskResponse
from src.application.use_case.aggregate_indicators_use_case import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_gate_audit import (
    GateContextCompleteness,
    GateEvaluationRecord,
)


class AssessRiskGateEvaluator:
    """Evaluates risk using the standard configured structural/execution gates."""

    def __init__(
        self,
        repository: MarketDataRepository,
        structural_gates: list[RiskGate],
        execution_gates: list[RiskGate],
        indicator_history_days: int,
        gate_recent_candle_lookback: int,
    ) -> None:
        self._repository = repository
        self._structural_gates = structural_gates
        self._execution_gates = execution_gates
        self._indicator_history_days = indicator_history_days
        self._gate_recent_candle_lookback = gate_recent_candle_lookback

    def evaluate(self, request: AssessRiskRequest) -> AssessRiskResponse:
        """
        Evaluate risk for a ticker using configured structural/execution gates.

        Verdict short-circuit is unchanged. Package C2 also records every
        configured gate as evaluated / not_evaluated for child-table audit.

        Raises:
            ValueError: If ticker invalid or insufficient data
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

        latest_snapshot = agg_response.snapshots[-1]
        # Gate evaluation — build enriched context, then run gates.
        # Structural gates short-circuit first (BLOCKED_STRUCTURAL);
        # execution gates run after (BLOCKED_EXECUTION).
        gate_ctx = self._build_gate_context(
            request, latest_snapshot.date, latest_snapshot
        )
        completeness = (
            GateContextCompleteness.from_context(gate_ctx) if gate_ctx is not None else None
        )

        firing_gate: RiskGate | None = None
        firing_result = None
        firing_structural: bool | None = None
        evaluations: list[GateEvaluationRecord] = []
        short_circuited = False
        order = 0

        if gate_ctx is not None:
            for gate in self._structural_gates:
                if short_circuited:
                    evaluations.append(
                        GateEvaluationRecord.not_evaluated(
                            gate_name=type(gate).__name__,
                            tier="structural",
                            order=order,
                        )
                    )
                    order += 1
                    continue
                gate_result = gate.evaluate(gate_ctx)
                evaluations.append(
                    GateEvaluationRecord.from_result(
                        gate_name=type(gate).__name__,
                        tier="structural",
                        order=order,
                        result=gate_result,
                    )
                )
                order += 1
                if gate_result.triggered:
                    firing_gate = gate
                    firing_result = gate_result
                    firing_structural = True
                    short_circuited = True

            for gate in self._execution_gates:
                if short_circuited:
                    evaluations.append(
                        GateEvaluationRecord.not_evaluated(
                            gate_name=type(gate).__name__,
                            tier="execution",
                            order=order,
                        )
                    )
                    order += 1
                    continue
                gate_result = gate.evaluate(gate_ctx)
                evaluations.append(
                    GateEvaluationRecord.from_result(
                        gate_name=type(gate).__name__,
                        tier="execution",
                        order=order,
                        result=gate_result,
                    )
                )
                order += 1
                if gate_result.triggered:
                    firing_gate = gate
                    firing_result = gate_result
                    firing_structural = False
                    short_circuited = True

        if firing_gate is not None and firing_result is not None:
            return self._gate_response(
                agg_response,
                request,
                latest_snapshot,
                firing_gate,
                firing_result,
                is_structural=bool(firing_structural),
                gate_evaluations=tuple(evaluations),
                gate_context_completeness=completeness,
            )

        assessment = RiskAssessment(
            rationale=("all gates passed",),
            snapshot_date=latest_snapshot.date,
            indicators=latest_snapshot,
            gate_triggered=None,
        )
        return AssessRiskResponse(
            ticker=agg_response.ticker,
            assessment=assessment,
            sma_period=request.sma_period,
            ema_period=request.ema_period,
            rsi_period=request.rsi_period,
            coverage_warning=agg_response.coverage_warning,
            gate_evaluations=tuple(evaluations),
            gate_context_completeness=completeness,
        )

    def _gate_response(
        self,
        agg_response,
        request: AssessRiskRequest,
        latest_snapshot: IndicatorSnapshot,
        gate: RiskGate,
        gate_result,
        is_structural: bool,
        gate_evaluations: tuple[GateEvaluationRecord, ...] = (),
        gate_context_completeness: GateContextCompleteness | None = None,
    ) -> AssessRiskResponse:
        assessment = RiskAssessment(
            rationale=(gate_result.reason,),
            snapshot_date=latest_snapshot.date,
            indicators=latest_snapshot,
            gate_triggered=type(gate).__name__,
            gate_is_structural=is_structural,
            gate_confidence=gate_result.confidence,
        )
        return AssessRiskResponse(
            ticker=agg_response.ticker,
            assessment=assessment,
            sma_period=request.sma_period,
            ema_period=request.ema_period,
            rsi_period=request.rsi_period,
            coverage_warning=agg_response.coverage_warning,
            gate_evaluations=gate_evaluations,
            gate_context_completeness=gate_context_completeness,
        )

    def _build_gate_context(
        self,
        request: AssessRiskRequest,
        snapshot_date: date,
        latest_snapshot: IndicatorSnapshot | None = None,
    ) -> GateContext | None:
        """
        Return an enriched GateContext for gate evaluation.

        If request.gate_context is None or no gates are configured, returns None.
        Enriches the caller-provided context with recent candles (for LiquidityGate)
        from the repository and the latest indicator snapshot (for TechnicalGate).
        """
        if request.gate_context is None:
            return None
        if not self._structural_gates and not self._execution_gates:
            return None

        ctx = request.gate_context
        # Enrich with candles for LiquidityGate only if not already provided.
        # Use snapshot_date as end_date to prevent look-ahead in backtests.
        if not ctx.recent_candles:
            candles = self._repository.get_candles(
                request.ticker.upper(),
                end_date=snapshot_date,
            )
            ctx = replace(ctx, recent_candles=tuple(candles[-self._gate_recent_candle_lookback:]))
        if latest_snapshot is not None and ctx.latest_snapshot is None:
            ctx = replace(ctx, latest_snapshot=latest_snapshot)
        return ctx
