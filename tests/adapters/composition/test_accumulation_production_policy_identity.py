"""Corpus wiring must inject the same policy objects into engines and snapshots."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.adapters.composition.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow_bundle,
)
from src.application.services.accumulation_production_policy_bundle import (
    AccumulationProductionPolicyBundle,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
)


def test_workflow_bundle_injects_exact_policy_object_identity(tmp_path: Path) -> None:
    accum = AccumScorePolicy()
    signal_cfg = SignalEngineConfig()
    structural = (FundamentalGate(),)
    execution = (BandarGate(),)
    bundle = AccumulationProductionPolicyBundle(
        accum_score_policy=accum,
        signal_engine_config=signal_cfg,
        structural_gates=structural,
        execution_gates=execution,
    )
    screener = AccumulationScreenerConfig(accum_score_policy=accum)

    deps = MagicMock()
    deps.market_repository = MagicMock()
    deps.broker_repository = MagicMock()
    deps.stockbit_providers = MagicMock()
    deps.learning_artifact_repository = MagicMock()
    deps.indicator_registry_factory.return_value = MagicMock()
    deps.rules_loader_factory.return_value = MagicMock()
    deps.ticker_profile_classifier_factory = MagicMock()
    deps.institutional_accumulation_config_factory = MagicMock()
    deps.sector_context_builder_factory = MagicMock()
    deps.sector_macro_context_builder_factory = MagicMock()
    deps.company_quality_context_builder_factory = MagicMock()

    with (
        patch(
            "src.adapters.composition.screen_accum_workflow_factory.create_accumulation_assess_risk_use_case"
        ) as mock_risk,
        patch(
            "src.adapters.composition.screen_accum_workflow_factory.create_signal_engine"
        ) as mock_signal,
        patch(
            "src.adapters.composition.screen_accum_workflow_factory.create_accumulation_screen_use_case_bundle"
        ) as mock_bundle,
        patch(
            "src.adapters.composition.screen_accum_workflow_factory.SQLiteMacroCalendarRepository"
        ),
        patch("src.adapters.composition.screen_accum_workflow_factory._setup_phase_history_repo"),
    ):
        mock_risk.return_value = MagicMock()
        mock_signal.return_value = MagicMock()
        mock_bundle.return_value = MagicMock()

        create_accumulation_screen_workflow_bundle(
            db_path=tmp_path / "data.db",
            screener_config=screener,
            production_policy_bundle=bundle,
            dependencies=deps,
        )

        risk_kwargs = mock_risk.call_args.kwargs
        assert risk_kwargs["structural_gates"] is structural
        assert risk_kwargs["execution_gates"] is execution

        signal_kwargs = mock_signal.call_args.kwargs
        assert signal_kwargs["config"] is signal_cfg
        assert signal_kwargs["with_enrichment"] is True

        bundle_kwargs = mock_bundle.call_args.kwargs
        assert bundle_kwargs["accum_score_policy"] is accum
        assert bundle_kwargs["signal_engine"] is mock_signal.return_value
        assert bundle_kwargs["risk_use_case"] is mock_risk.return_value


def test_mismatched_accum_score_policy_objects_fail_closed(tmp_path: Path) -> None:
    import pytest

    accum_a = AccumScorePolicy()
    accum_b = AccumScorePolicy()
    bundle = AccumulationProductionPolicyBundle(
        accum_score_policy=accum_a,
        signal_engine_config=SignalEngineConfig(),
        structural_gates=(FundamentalGate(),),
        execution_gates=(BandarGate(),),
    )
    screener = AccumulationScreenerConfig(accum_score_policy=accum_b)
    with pytest.raises(ValueError, match="same object"):
        create_accumulation_screen_workflow_bundle(
            db_path=tmp_path / "data.db",
            screener_config=screener,
            production_policy_bundle=bundle,
            dependencies=MagicMock(),
        )
