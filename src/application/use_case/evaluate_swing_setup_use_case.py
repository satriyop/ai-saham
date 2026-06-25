"""
Evaluate named swing setups against accumulation candidates.

Layer: Application
AI usage: None
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from src.domain.value_objects.setup_evaluation import (
    SetupEvaluation,
    SetupGate,
    SetupMatch,
)


FOREIGN_BOUNCE_SETUP = "foreign-bounce"
COILED_SPRING_SETUP = "coiled-spring"
SMART_MONEY_CONFIRMED_SETUP = "smart-money-confirmed"
PULLBACK_CONTINUATION_SETUP = "pullback-continuation"
AVAILABLE_SWING_SETUPS = (
    FOREIGN_BOUNCE_SETUP,
    COILED_SPRING_SETUP,
    SMART_MONEY_CONFIRMED_SETUP,
    PULLBACK_CONTINUATION_SETUP,
)


@dataclass(frozen=True)
class ForeignBounceSetupConfig:
    gate_min_score: float = 70.0
    gate_min_vwap_discount_pct: float = 3.0
    gate_required_trend: str = "SIDE"
    gate_min_flow_ratio_pct: float = 5.0
    gate_max_rsi: float = 60.0
    partial_max_failed_gates: int = 2
    enabled: bool = True


@dataclass(frozen=True)
class CoiledSpringSetupConfig:
    gate_min_score: float = 60.0
    gate_max_bb_width_pctile: float = 0.20
    gate_min_flow_ratio_pct: float = 3.0
    gate_max_rsi: float = 65.0
    partial_max_failed_gates: int = 2
    enabled: bool = True


@dataclass(frozen=True)
class SmartMoneyConfirmedSetupConfig:
    gate_min_score: float = 60.0
    gate_min_smart_flow_idr: Decimal = Decimal("0")
    gate_min_smart_share_pct: float = 30.0
    gate_max_noise_share_pct: float = 60.0
    reject_smart_net_selling: bool = True
    partial_max_failed_gates: int = 1
    enabled: bool = True


@dataclass(frozen=True)
class PullbackContinuationSetupConfig:
    gate_min_score: float = 55.0
    gate_required_trend: str = "UP"
    gate_min_flow_ratio_pct: float = 2.0
    gate_min_rsi: float = 40.0
    gate_max_rsi: float = 65.0
    gate_min_vwap_discount_pct: float = -2.0
    partial_max_failed_gates: int = 2
    enabled: bool = True


@dataclass(frozen=True)
class SwingSetupCatalogConfig:
    foreign_bounce: ForeignBounceSetupConfig = field(
        default_factory=ForeignBounceSetupConfig
    )
    coiled_spring: CoiledSpringSetupConfig = field(
        default_factory=CoiledSpringSetupConfig
    )
    smart_money_confirmed: SmartMoneyConfirmedSetupConfig = field(
        default_factory=SmartMoneyConfirmedSetupConfig
    )
    pullback_continuation: PullbackContinuationSetupConfig = field(
        default_factory=PullbackContinuationSetupConfig
    )

    def config_for(self, setup_name: str) -> Any:
        setup_key = setup_name.lower()
        if setup_key == FOREIGN_BOUNCE_SETUP:
            return self.foreign_bounce
        if setup_key == COILED_SPRING_SETUP:
            return self.coiled_spring
        if setup_key == SMART_MONEY_CONFIRMED_SETUP:
            return self.smart_money_confirmed
        if setup_key == PULLBACK_CONTINUATION_SETUP:
            return self.pullback_continuation
        raise ValueError(f"Unsupported swing setup: {setup_name}")


@dataclass(frozen=True)
class EvaluateSwingSetupRequest:
    setup_name: str
    candidate: object | None
    config: SwingSetupCatalogConfig
    broker_detail: object | None = None


def _fmt_gate_value(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "None"
    return f"{value:.1f}{suffix}"


class EvaluateSwingSetupUseCase:
    """Deterministic setup-fit evaluator for swing workflows."""

    def execute(self, request: EvaluateSwingSetupRequest) -> SetupEvaluation:
        setup_name = request.setup_name.lower()
        config = request.config.config_for(setup_name)
        if not config.enabled:
            return SetupEvaluation(
                name=setup_name,
                match=SetupMatch.NO_MATCH,
                gates=(SetupGate("setup enabled", False, "false", "true"),),
                failed_reasons=("setup enabled: false (required true)",),
            )
        if setup_name == FOREIGN_BOUNCE_SETUP:
            return self._foreign_bounce(request.candidate, config)
        if setup_name == COILED_SPRING_SETUP:
            return self._coiled_spring(request.candidate, config)
        if setup_name == SMART_MONEY_CONFIRMED_SETUP:
            return self._smart_money_confirmed(
                request.candidate,
                request.broker_detail,
                config,
            )
        if setup_name == PULLBACK_CONTINUATION_SETUP:
            return self._pullback_continuation(request.candidate, config)
        raise ValueError(f"Unsupported swing setup: {request.setup_name}")

    def _missing_candidate(self, setup_name: str) -> SetupEvaluation:
        return SetupEvaluation(
            name=setup_name,
            match=SetupMatch.NO_MATCH,
            gates=(
                SetupGate(
                    label="broker flow data",
                    passed=False,
                    actual="missing",
                    required="available",
                ),
            ),
            failed_reasons=("No accumulation/broker-flow candidate available",),
        )

    def _evaluation(
        self,
        *,
        setup_name: str,
        gates: tuple[SetupGate, ...],
        partial_max_failed_gates: int,
        force_partial_when_score_passes: bool = False,
    ) -> SetupEvaluation:
        failed = tuple(
            f"{gate.label}: {gate.actual} (required {gate.required})"
            for gate in gates
            if not gate.passed
        )
        if not failed:
            match = SetupMatch.MATCH
        elif force_partial_when_score_passes or len(failed) <= partial_max_failed_gates:
            match = SetupMatch.PARTIAL
        else:
            match = SetupMatch.NO_MATCH
        return SetupEvaluation(
            name=setup_name,
            match=match,
            gates=gates,
            failed_reasons=failed,
        )

    def _foreign_bounce(
        self,
        candidate: object | None,
        config: ForeignBounceSetupConfig,
    ) -> SetupEvaluation:
        if candidate is None:
            return self._missing_candidate(FOREIGN_BOUNCE_SETUP)

        gates = (
            SetupGate(
                label="score",
                passed=candidate.score >= config.gate_min_score,
                actual=f"{candidate.score:.1f}",
                required=f">= {config.gate_min_score:.0f}",
            ),
            SetupGate(
                label="fvwap%",
                passed=(
                    candidate.vwap_discount_pct is not None
                    and candidate.vwap_discount_pct >= config.gate_min_vwap_discount_pct
                ),
                actual=_fmt_gate_value(candidate.vwap_discount_pct, "%"),
                required=f">= +{config.gate_min_vwap_discount_pct:.0f}%",
            ),
            SetupGate(
                label="trend",
                passed=candidate.trend == config.gate_required_trend,
                actual=candidate.trend,
                required=config.gate_required_trend,
            ),
            SetupGate(
                label="flow_pct",
                passed=(
                    candidate.avg_flow_ratio is not None
                    and candidate.avg_flow_ratio >= config.gate_min_flow_ratio_pct
                ),
                actual=_fmt_gate_value(candidate.avg_flow_ratio, "%"),
                required=f">= +{config.gate_min_flow_ratio_pct:.0f}%",
            ),
            SetupGate(
                label="RSI present",
                passed=candidate.rsi is not None,
                actual=_fmt_gate_value(candidate.rsi),
                required="present",
            ),
            SetupGate(
                label="RSI",
                passed=candidate.rsi is not None and candidate.rsi <= config.gate_max_rsi,
                actual=_fmt_gate_value(candidate.rsi),
                required=f"<= {config.gate_max_rsi:.0f}",
            ),
        )
        return self._evaluation(
            setup_name=FOREIGN_BOUNCE_SETUP,
            gates=gates,
            partial_max_failed_gates=config.partial_max_failed_gates,
            force_partial_when_score_passes=candidate.score >= config.gate_min_score,
        )

    def _coiled_spring(
        self,
        candidate: object | None,
        config: CoiledSpringSetupConfig,
    ) -> SetupEvaluation:
        if candidate is None:
            return self._missing_candidate(COILED_SPRING_SETUP)

        gates = (
            SetupGate(
                label="score",
                passed=candidate.score >= config.gate_min_score,
                actual=f"{candidate.score:.1f}",
                required=f">= {config.gate_min_score:.0f}",
            ),
            SetupGate(
                label="bb_width_pctile",
                passed=(
                    candidate.bb_width_pctile is not None
                    and candidate.bb_width_pctile <= config.gate_max_bb_width_pctile
                ),
                actual=_fmt_gate_value(candidate.bb_width_pctile),
                required=f"<= {config.gate_max_bb_width_pctile:.2f}",
            ),
            SetupGate(
                label="flow_pct",
                passed=(
                    candidate.avg_flow_ratio is not None
                    and candidate.avg_flow_ratio >= config.gate_min_flow_ratio_pct
                ),
                actual=_fmt_gate_value(candidate.avg_flow_ratio, "%"),
                required=f">= +{config.gate_min_flow_ratio_pct:.0f}%",
            ),
            SetupGate(
                label="RSI present",
                passed=candidate.rsi is not None,
                actual=_fmt_gate_value(candidate.rsi),
                required="present",
            ),
            SetupGate(
                label="RSI",
                passed=candidate.rsi is not None and candidate.rsi <= config.gate_max_rsi,
                actual=_fmt_gate_value(candidate.rsi),
                required=f"<= {config.gate_max_rsi:.0f}",
            ),
        )
        return self._evaluation(
            setup_name=COILED_SPRING_SETUP,
            gates=gates,
            partial_max_failed_gates=config.partial_max_failed_gates,
            force_partial_when_score_passes=candidate.score >= config.gate_min_score,
        )

    def _smart_money_confirmed(
        self,
        candidate: object | None,
        broker_detail: object | None,
        config: SmartMoneyConfirmedSetupConfig,
    ) -> SetupEvaluation:
        if candidate is None:
            return self._missing_candidate(SMART_MONEY_CONFIRMED_SETUP)
        if broker_detail is None:
            gate = SetupGate(
                label="broker detail",
                passed=False,
                actual="missing",
                required="available",
            )
            return SetupEvaluation(
                name=SMART_MONEY_CONFIRMED_SETUP,
                match=SetupMatch.NO_MATCH,
                gates=(gate,),
                failed_reasons=("broker detail: missing (required available)",),
            )

        smart_flow = getattr(broker_detail, "smart_flow", Decimal("0"))
        noise_flow = getattr(broker_detail, "noise_flow", Decimal("0"))
        neutral_flow = getattr(broker_detail, "neutral_flow", Decimal("0"))
        total_abs = abs(smart_flow) + abs(noise_flow) + abs(neutral_flow)
        noise_share_pct = (
            float(abs(noise_flow) / total_abs * Decimal("100"))
            if total_abs > Decimal("0") else None
        )
        smart_share_pct = getattr(broker_detail, "smart_share_pct", None)

        gates = (
            SetupGate(
                label="score",
                passed=candidate.score >= config.gate_min_score,
                actual=f"{candidate.score:.1f}",
                required=f">= {config.gate_min_score:.0f}",
            ),
            SetupGate(
                label="smart_flow",
                passed=smart_flow >= config.gate_min_smart_flow_idr,
                actual=str(smart_flow),
                required=f">= {config.gate_min_smart_flow_idr}",
            ),
            SetupGate(
                label="smart_share_pct",
                passed=(
                    smart_share_pct is not None
                    and smart_share_pct >= config.gate_min_smart_share_pct
                ),
                actual=_fmt_gate_value(smart_share_pct, "%"),
                required=f">= {config.gate_min_smart_share_pct:.0f}%",
            ),
            SetupGate(
                label="noise_share_pct",
                passed=(
                    noise_share_pct is not None
                    and noise_share_pct <= config.gate_max_noise_share_pct
                ),
                actual=_fmt_gate_value(noise_share_pct, "%"),
                required=f"<= {config.gate_max_noise_share_pct:.0f}%",
            ),
            SetupGate(
                label="smart_net_selling",
                passed=(smart_flow >= Decimal("0"))
                if config.reject_smart_net_selling else True,
                actual="true" if smart_flow < Decimal("0") else "false",
                required="false",
            ),
        )
        return self._evaluation(
            setup_name=SMART_MONEY_CONFIRMED_SETUP,
            gates=gates,
            partial_max_failed_gates=config.partial_max_failed_gates,
            force_partial_when_score_passes=candidate.score >= config.gate_min_score,
        )

    def _pullback_continuation(
        self,
        candidate: object | None,
        config: PullbackContinuationSetupConfig,
    ) -> SetupEvaluation:
        if candidate is None:
            return self._missing_candidate(PULLBACK_CONTINUATION_SETUP)

        gates = (
            SetupGate(
                label="score",
                passed=candidate.score >= config.gate_min_score,
                actual=f"{candidate.score:.1f}",
                required=f">= {config.gate_min_score:.0f}",
            ),
            SetupGate(
                label="trend",
                passed=candidate.trend == config.gate_required_trend,
                actual=candidate.trend,
                required=config.gate_required_trend,
            ),
            SetupGate(
                label="flow_pct",
                passed=(
                    candidate.avg_flow_ratio is not None
                    and candidate.avg_flow_ratio >= config.gate_min_flow_ratio_pct
                ),
                actual=_fmt_gate_value(candidate.avg_flow_ratio, "%"),
                required=f">= +{config.gate_min_flow_ratio_pct:.0f}%",
            ),
            SetupGate(
                label="RSI lower",
                passed=candidate.rsi is not None and candidate.rsi >= config.gate_min_rsi,
                actual=_fmt_gate_value(candidate.rsi),
                required=f">= {config.gate_min_rsi:.0f}",
            ),
            SetupGate(
                label="RSI upper",
                passed=candidate.rsi is not None and candidate.rsi <= config.gate_max_rsi,
                actual=_fmt_gate_value(candidate.rsi),
                required=f"<= {config.gate_max_rsi:.0f}",
            ),
            SetupGate(
                label="fvwap%",
                passed=(
                    candidate.vwap_discount_pct is not None
                    and candidate.vwap_discount_pct >= config.gate_min_vwap_discount_pct
                ),
                actual=_fmt_gate_value(candidate.vwap_discount_pct, "%"),
                required=f">= {config.gate_min_vwap_discount_pct:.1f}%",
            ),
        )
        return self._evaluation(
            setup_name=PULLBACK_CONTINUATION_SETUP,
            gates=gates,
            partial_max_failed_gates=config.partial_max_failed_gates,
            force_partial_when_score_passes=candidate.score >= config.gate_min_score,
        )
