"""
Factory for accumulation screen risk use case wiring.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_risk_gates,
    resolve_unevaluable_gate_policy,
)
from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import RiskGate, UnevaluableGatePolicy
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.engine_config_loader import load_engine_config


def create_accumulation_assess_risk_use_case(
    *,
    market_repository: MarketDataRepository,
    risk_config_path: Path | None = None,
    structural_gates: Sequence[RiskGate] | None = None,
    execution_gates: Sequence[RiskGate] | None = None,
    unevaluable_gate_policy: UnevaluableGatePolicy | None = None,
) -> AssessRiskUseCase:
    """Build the AssessRiskUseCase used by accumulation screen workflows.

    When both ``structural_gates`` and ``execution_gates`` are provided, they are
    injected by identity (no second risk YAML resolve). Providing only one is
    a programming error and fails closed.

    ``unevaluable_gate_policy`` follows the same rule: callers that inject gates
    by identity must inject the policy resolved from the same config load
    (see ``AccumulationProductionPolicyBundle``). Otherwise it is resolved from
    the same risk YAML as the gates.
    """
    if (structural_gates is None) ^ (execution_gates is None):
        raise ValueError(
            "structural_gates and execution_gates must both be provided or both omitted"
        )
    if structural_gates is None:
        cfg = load_app_config()
        config_path = risk_config_path or Path(cfg.config_paths.risk_engine)
        engine_config = load_engine_config(config_path)
        structural_gates, execution_gates = resolve_risk_gates(engine_config)
        if unevaluable_gate_policy is None:
            unevaluable_gate_policy = resolve_unevaluable_gate_policy(engine_config)
    return AssessRiskUseCase(
        repository=market_repository,
        structural_gates=list(structural_gates),
        execution_gates=list(execution_gates),
        unevaluable_gate_policy=unevaluable_gate_policy,
    )
