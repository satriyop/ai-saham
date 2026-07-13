from unittest.mock import MagicMock

from src.adapters.cli.accumulation_risk_workflow_factory import (
    create_accumulation_assess_risk_use_case,
)
from src.application.use_case.assess_risk_use_case import AssessRiskUseCase


def test_loads_configured_risk_file_and_returns_assess_risk_use_case():
    market_repository = MagicMock()

    use_case = create_accumulation_assess_risk_use_case(
        market_repository=market_repository,
    )

    assert isinstance(use_case, AssessRiskUseCase)
    assert len(use_case._gate_evaluator._structural_gates) > 0
    assert len(use_case._gate_evaluator._execution_gates) > 0


def test_passes_provided_market_repository_into_use_case():
    market_repository = MagicMock()

    use_case = create_accumulation_assess_risk_use_case(
        market_repository=market_repository,
    )

    assert use_case._repository is market_repository


def test_disabled_gates_in_custom_config_remain_disabled(tmp_path):
    risk_config_path = tmp_path / "risk.yaml"
    risk_config_path.write_text(
        """
version: 1
risk_engine:
  gates:
    fundamental:
      enabled: false
    liquidity:
      enabled: false
    free_float:
      enabled: false
    bandar:
      enabled: false
"""
    )
    market_repository = MagicMock()

    use_case = create_accumulation_assess_risk_use_case(
        market_repository=market_repository,
        risk_config_path=risk_config_path,
    )

    assert use_case._gate_evaluator._structural_gates == []
    assert use_case._gate_evaluator._execution_gates == []


def test_accepts_custom_risk_config_path_not_only_global_app_cfg(tmp_path):
    risk_config_path = tmp_path / "custom_risk.yaml"
    risk_config_path.write_text(
        """
version: 1
risk_engine:
  gates:
    fundamental:
      enabled: false
    liquidity:
      enabled: true
    free_float:
      enabled: false
    bandar:
      enabled: false
"""
    )
    market_repository = MagicMock()

    use_case = create_accumulation_assess_risk_use_case(
        market_repository=market_repository,
        risk_config_path=risk_config_path,
    )

    assert len(use_case._gate_evaluator._structural_gates) == 1
    assert use_case._gate_evaluator._execution_gates == []
