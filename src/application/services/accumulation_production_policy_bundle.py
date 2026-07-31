"""Typed production-policy objects shared by engines and snapshot export.

Layer: Application (pure value object). No I/O.

Callers that write accumulation observations and production policy snapshots
must resolve this bundle once and inject the same objects into SignalEngine,
AssessRiskUseCase, ScoreAccumUseCase policy, and snapshot ensure.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.risk_gate import RiskGate


@dataclass(frozen=True)
class AccumulationProductionPolicyBundle:
    """Exact typed policies for one accumulation corpus write invocation."""

    accum_score_policy: AccumScorePolicy
    signal_engine_config: SignalEngineConfig
    structural_gates: tuple[RiskGate, ...]
    execution_gates: tuple[RiskGate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.accum_score_policy, AccumScorePolicy):
            raise TypeError(
                "accum_score_policy must be AccumScorePolicy, got "
                f"{type(self.accum_score_policy).__name__}"
            )
        if not isinstance(self.signal_engine_config, SignalEngineConfig):
            raise TypeError(
                "signal_engine_config must be SignalEngineConfig, got "
                f"{type(self.signal_engine_config).__name__}"
            )
        if not isinstance(self.structural_gates, tuple):
            raise TypeError("structural_gates must be a tuple")
        if not isinstance(self.execution_gates, tuple):
            raise TypeError("execution_gates must be a tuple")
