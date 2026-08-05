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
from src.domain.rules.risk_gate import GateContext, RiskGate, UnevaluableGatePolicy
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_gate_audit import (
    GateContextCompleteness,
    GateEvaluationRecord,
)


def _unevaluable_records(
    evaluations: list[GateEvaluationRecord],
) -> tuple[GateEvaluationRecord, ...]:
    """Gates that ran but had no usable input, in evaluation order."""
    return tuple(row for row in evaluations if row.is_unevaluable)


def _unevaluable_block_rationale(rows: tuple[GateEvaluationRecord, ...]) -> str:
    names = ", ".join(row.gate for row in rows)
    noun = "gate" if len(rows) == 1 else "gates"
    return (
        f"{len(rows)} {noun} unevaluable ({names}); blocked by "
        "risk_engine.gates.unevaluable_policy=block"
    )


def _no_gate_fired_rationale(unevaluable_gates: tuple[str, ...]) -> str:
    """Rationale when nothing fired — never claim a clean sweep we did not get."""
    if not unevaluable_gates:
        return "all gates passed"
    count = len(unevaluable_gates)
    noun = "gate" if count == 1 else "gates"
    return f"no gate blocked; {count} {noun} unevaluable ({', '.join(unevaluable_gates)})"


class AssessRiskGateEvaluator:
    """Evaluates risk using the standard configured structural/execution gates."""

    def __init__(
        self,
        repository: MarketDataRepository,
        structural_gates: list[RiskGate],
        execution_gates: list[RiskGate],
        indicator_history_days: int,
        gate_recent_candle_lookback: int,
        unevaluable_gate_policy: UnevaluableGatePolicy | None = None,
    ) -> None:
        self._repository = repository
        self._structural_gates = structural_gates
        self._execution_gates = execution_gates
        self._indicator_history_days = indicator_history_days
        self._gate_recent_candle_lookback = gate_recent_candle_lookback
        self._unevaluable_gate_policy = unevaluable_gate_policy or UnevaluableGatePolicy()

    @property
    def unevaluable_gate_policy(self) -> UnevaluableGatePolicy:
        """Resolved aggregate policy for gates that ran without usable input."""
        return self._unevaluable_gate_policy

    def evaluate(self, request: AssessRiskRequest) -> AssessRiskResponse:
        """
        Evaluate risk for a ticker using configured structural/execution gates.

        Verdict short-circuit is unchanged. Package C2 also records every
        configured gate as evaluated / not_evaluated for child-table audit.

        Raises:
            ValueError: If ticker invalid or insufficient data
        """
        # PIT cutoff validation — must run before any repository read.
        # AssessRiskRequest.as_of_date is the sole cutoff authority; when it is
        # set, GateContext.snapshot_date must agree with it. Disagreement is a
        # contract error, never silently reconciled.
        if (
            request.as_of_date is not None
            and request.gate_context is not None
            and request.gate_context.snapshot_date != request.as_of_date
        ):
            raise ValueError(
                f"as_of_date ({request.as_of_date}) does not match "
                f"gate_context.snapshot_date ({request.gate_context.snapshot_date}); "
                "the risk-path cutoff and the gate-context session date must agree"
            )

        agg_use_case = AggregateIndicatorsUseCase(self._repository)
        agg_response = agg_use_case.execute(
            AggregateIndicatorsRequest(
                ticker=request.ticker,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
                days=self._indicator_history_days,
                as_of_date=request.as_of_date,
            )
        )

        if not agg_response.has_values:
            ticker_upper = request.ticker.upper()
            if request.as_of_date is not None:
                # Never retry unbounded — that would reintroduce the look-ahead.
                # The fetch hint still applies: the cache may simply lack history
                # covering the cutoff window. Live callers pass today as the
                # cutoff, so this is also the ordinary "not fetched yet" message.
                raise ValueError(
                    f"Insufficient data for {ticker_upper} at or before cutoff "
                    f"{request.as_of_date}: no indicator values available on or "
                    f"before that date. Run 'saham fetch market {ticker_upper} "
                    f"--days {self._indicator_history_days}' if the local cache "
                    "lacks history for that window."
                )
            raise ValueError(
                f"Insufficient data for {ticker_upper}. Run "
                f"'saham fetch market {ticker_upper} --days "
                f"{self._indicator_history_days}' first."
            )

        latest_snapshot = agg_response.snapshots[-1]
        # Gate evaluation — build enriched context, then run gates.
        # Structural gates short-circuit first (BLOCKED_STRUCTURAL);
        # execution gates run after (BLOCKED_EXECUTION).
        gate_ctx = self._build_gate_context(request, latest_snapshot.date, latest_snapshot)
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

        unevaluable_rows = _unevaluable_records(evaluations)
        unevaluable = tuple(row.gate for row in unevaluable_rows)

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
                unevaluable_gates=unevaluable,
            )

        # No gate fired. The configured aggregate policy decides whether the
        # unknowns themselves block. Default (`surface`) never does, so the
        # action distribution is unchanged from before the policy existed.
        if unevaluable_rows and self._unevaluable_gate_policy.blocks:
            first = unevaluable_rows[0]
            assessment = RiskAssessment(
                rationale=(_unevaluable_block_rationale(unevaluable_rows),),
                snapshot_date=latest_snapshot.date,
                indicators=latest_snapshot,
                gate_triggered=first.gate,
                gate_is_structural=first.tier == "structural",
                gate_confidence=self._unevaluable_gate_policy.block_confidence,
                unevaluable_gates=unevaluable,
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

        assessment = RiskAssessment(
            rationale=(_no_gate_fired_rationale(unevaluable),),
            snapshot_date=latest_snapshot.date,
            indicators=latest_snapshot,
            gate_triggered=None,
            unevaluable_gates=unevaluable,
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
        unevaluable_gates: tuple[str, ...] = (),
    ) -> AssessRiskResponse:
        assessment = RiskAssessment(
            rationale=(gate_result.reason,),
            snapshot_date=latest_snapshot.date,
            indicators=latest_snapshot,
            gate_triggered=type(gate).__name__,
            gate_is_structural=is_structural,
            gate_confidence=gate_result.confidence,
            unevaluable_gates=unevaluable_gates,
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
        # Bound the candle read by the PIT cutoff when one is set; otherwise use
        # the latest snapshot date (live). This is the sole look-ahead guard for
        # the LiquidityGate recent-candle leg — the cutoff, not the cache head.
        candle_end_date = request.as_of_date if request.as_of_date is not None else snapshot_date
        if not ctx.recent_candles:
            candles = self._repository.get_candles(
                request.ticker.upper(),
                end_date=candle_end_date,
            )
            ctx = replace(ctx, recent_candles=tuple(candles[-self._gate_recent_candle_lookback :]))
        if latest_snapshot is not None and ctx.latest_snapshot is None:
            ctx = replace(ctx, latest_snapshot=latest_snapshot)
        return ctx
