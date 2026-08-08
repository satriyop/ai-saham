"""RC-01B producer snapshot, binding, and persistence contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.application.config.market_context_config import MarketContextConfig
from src.application.dto.ticker_profile import TickerProfileConfig
from src.application.services.accumulation_diagnostic_producer_payloads import (
    AccumulationDiagnosticProducerInputs,
)
from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextConfig,
)
from src.application.services.institutional_flow_config import (
    InstitutionalAccumulationConfig,
)
from src.application.services.sector_context_evidence_builder import SectorContextConfig
from src.application.services.signal_engine_config import AlphaTriggerConfig
from src.application.services.signal_scoring_config import SignalScoringConfig
from src.application.use_case.ensure_accumulation_diagnostic_producer_snapshots_use_case import (
    EnsureAccumulationDiagnosticProducerSnapshotsRequest,
    EnsureAccumulationDiagnosticProducerSnapshotsUseCase,
)
from src.domain.value_objects.diagnostic_producer_identity import (
    ACCUMULATION_DIAGNOSTIC_REQUIRED_PRODUCERS,
    PRODUCER_ID_ALPHA_TRIGGER,
)
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)


def _inputs() -> AccumulationDiagnosticProducerInputs:
    return AccumulationDiagnosticProducerInputs(
        alpha_trigger_config=AlphaTriggerConfig(),
        sector_context_config=SectorContextConfig.from_mapping({}),
        sector_universe_index=(
            ("banks", ("BBCA", "BBRI")),
            ("conglomerates", ("ASII", "BBCA")),
        ),
        institutional_accumulation_config=InstitutionalAccumulationConfig.from_mapping({}),
        company_quality_context_config=CompanyQualityContextConfig.from_mapping({}),
        signal_scoring_config=SignalScoringConfig(),
        company_quality_neutral_score=50.0,
        ticker_profile_config=TickerProfileConfig.from_mapping({}),
        ticker_universe_index=(
            ("ASII", ("lq45",)),
            ("BBCA", ("lq45", "idx30")),
        ),
        market_context_config=MarketContextConfig(),
        market_context_universe=("ASII", "BBCA", "BBRI"),
    )


def _request(inputs: AccumulationDiagnosticProducerInputs):
    return EnsureAccumulationDiagnosticProducerSnapshotsRequest(
        inputs=inputs,
        created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        source_revision="ai-saham@test+git:rc01b",
    )


def test_real_payload_builder_persists_and_reopens_exact_closed_set(tmp_path):
    repo = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    use_case = EnsureAccumulationDiagnosticProducerSnapshotsUseCase(repo)

    first = use_case.execute(_request(_inputs()))
    second = use_case.execute(_request(_inputs()))

    assert first.inserted_count == 6
    assert first.reused_count == 0
    assert second.inserted_count == 0
    assert second.reused_count == 6
    assert set(first.bindings) == set(ACCUMULATION_DIAGNOSTIC_REQUIRED_PRODUCERS)
    reopened = repo.list_diagnostic_producer_snapshots(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        snapshot_ids=[snapshot.snapshot_id for snapshot in first.snapshots],
    )
    assert reopened == tuple(sorted(first.snapshots, key=lambda item: item.producer_id))


def test_alpha_trigger_mutation_forks_only_dependent_diagnostics(tmp_path):
    repo = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    use_case = EnsureAccumulationDiagnosticProducerSnapshotsUseCase(repo)
    base_inputs = _inputs()
    base = use_case.execute(_request(base_inputs))
    mutated_inputs = replace(
        base_inputs,
        alpha_trigger_config=replace(base_inputs.alpha_trigger_config, enabled=False),
    )
    mutated = use_case.execute(_request(mutated_inputs))

    base_snapshots = {snapshot.producer_id: snapshot for snapshot in base.snapshots}
    mutated_snapshots = {snapshot.producer_id: snapshot for snapshot in mutated.snapshots}
    assert (
        base_snapshots[PRODUCER_ID_ALPHA_TRIGGER].snapshot_id
        != mutated_snapshots[PRODUCER_ID_ALPHA_TRIGGER].snapshot_id
    )
    changed_bindings = {
        diagnostic_id
        for diagnostic_id in base.bindings
        if base.bindings[diagnostic_id].compatibility_id
        != mutated.bindings[diagnostic_id].compatibility_id
    }
    assert changed_bindings == {
        "sector.peer_context",
        "institutional.accumulation_bag",
        "company_quality.bag",
    }
    assert (
        base.bindings["mce.screen_display"].compatibility_id
        == mutated.bindings["mce.screen_display"].compatibility_id
    )


@pytest.mark.parametrize(
    ("producer", "expected_diagnostics"),
    [
        ("sector", {"sector.peer_context"}),
        ("institutional", {"institutional.accumulation_bag"}),
        ("company", {"company_quality.bag"}),
        ("ticker", {"company_quality.bag"}),
        ("market", {"mce.screen_display"}),
    ],
)
def test_independent_producer_mutation_forks_only_its_dependents(
    tmp_path, producer, expected_diagnostics
):
    repo = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    use_case = EnsureAccumulationDiagnosticProducerSnapshotsUseCase(repo)
    inputs = _inputs()
    base = use_case.execute(_request(inputs))
    if producer == "sector":
        mutated_inputs = replace(
            inputs,
            sector_context_config=replace(inputs.sector_context_config, min_peer_count=4),
        )
    elif producer == "institutional":
        mutated_inputs = replace(
            inputs,
            institutional_accumulation_config=replace(
                inputs.institutional_accumulation_config, foreign_vwap_days=21
            ),
        )
    elif producer == "company":
        mutated_inputs = replace(
            inputs,
            company_quality_neutral_score=51.0,
        )
    elif producer == "ticker":
        mutated_inputs = replace(
            inputs,
            ticker_profile_config=replace(inputs.ticker_profile_config, profile_window_days=31),
        )
    else:
        mutated_inputs = replace(
            inputs,
            market_context_config=replace(
                inputs.market_context_config,
                regime_thresholds=replace(
                    inputs.market_context_config.regime_thresholds,
                    risk_on_min_score=0.66,
                ),
            ),
        )
    mutated = use_case.execute(_request(mutated_inputs))
    changed = {
        diagnostic_id
        for diagnostic_id, binding in base.bindings.items()
        if binding.compatibility_id != mutated.bindings[diagnostic_id].compatibility_id
    }
    assert changed == expected_diagnostics
