"""
Factory for accumulation screen risk use case wiring.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_risk_gates,
)
from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
from src.domain.ports.market_data_repository import MarketDataRepository
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.engine_config_loader import load_engine_config


def create_accumulation_assess_risk_use_case(
    *,
    market_repository: MarketDataRepository,
    risk_config_path: Path | None = None,
) -> AssessRiskUseCase:
    """Build the AssessRiskUseCase used by accumulation screen workflows."""
    config_path = risk_config_path or Path(APP_CFG.config_paths.risk_engine)
    structural_gates, execution_gates = resolve_risk_gates(
        load_engine_config(config_path)
    )
    return AssessRiskUseCase(
        repository=market_repository,
        structural_gates=structural_gates,
        execution_gates=execution_gates,
    )
