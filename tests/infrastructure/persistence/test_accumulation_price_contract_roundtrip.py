from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.accumulation_candidate_observation_persister import (
    AccumulationCandidateObservationPersister,
)
from src.application.use_case.get_accumulation_producer_readiness_use_case import (
    GetAccumulationProducerReadinessUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import AccumPopulationBinding
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactReadRepository,
    SQLiteLearningArtifactRepository,
)
from tests.fixtures.diagnostic_producer_identity import (
    valid_accumulation_diagnostic_bindings,
)


def test_real_persister_decimal_text_survives_sqlite_and_readiness(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "data.db"
    write_repo = SQLiteLearningArtifactRepository(db_path)
    persister = AccumulationCandidateObservationPersister(
        candidate_observations_repository=write_repo,
        candidate_evidence_builder=None,  # type: ignore[arg-type]
        setup_family_resolver=None,  # type: ignore[arg-type]
        swing_setup_catalog=None,
    )
    structural_filter = {
        "outcome": "disabled",
        "field": None,
        "reason": None,
        "observed_value": None,
        "threshold": None,
    }
    monkeypatch.setattr(
        persister,
        "_build_engine_pack",
        lambda *args, **kwargs: {"structural_filter": structural_filter},
    )
    candidate = SimpleNamespace(ticker="BBCA", current_price=Decimal("2510.00"))
    observation_candidate = SimpleNamespace(candidate=candidate, screen_result="pass")
    request = SimpleNamespace(market_context=None)
    session_date = date(2026, 8, 7)
    session = SimpleNamespace(
        decision_at=datetime(2026, 8, 7, 16, 0, tzinfo=IDX_TIMEZONE),
        latest_completed_session=session_date,
        analysis_as_of=session_date,
        market_session_name="regular",
        is_eod_pending=False,
        resolution_source="test",
        notes=(),
    )
    binding = AccumPopulationBinding.create(
        membership_tickers=["BBCA"],
        named_universe_tickers=["ASII", "BBCA", "BBRI"],
        membership_session=session_date,
        pit_tradable_lookback_sessions=10,
        producer_source_revision="ai-saham@test+git:grow01",
    )
    compatibility_id = SemanticCompatibilityId("sha256:" + "a" * 64)

    saved = persister.persist_session_multi_window(
        window_results={
            7: (request, [observation_candidate]),
            30: (request, [observation_candidate]),
            90: (request, [observation_candidate]),
        },
        snapshot_date=session_date,
        effective_session=session,
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=compatibility_id,
        universe_tickers=["BBCA"],
        population_binding=binding,
        diagnostic_bindings=valid_accumulation_diagnostic_bindings(),
    )
    assert saved == 1

    size_before_read = db_path.stat().st_size
    read_repo = SQLiteLearningArtifactReadRepository(db_path)
    report = GetAccumulationProducerReadinessUseCase(
        observations=read_repo,
        labels=read_repo,
        policy_snapshots=read_repo,
    ).execute()

    assert db_path.stat().st_size == size_before_read
    assert report.observation_count == 1
    cohort = report.cohorts[0]
    assert cohort.observation_validation.valid_observation_count == 1
    assert cohort.observation_validation.invalid_observation_count == 0
    loaded = read_repo.list_observations(report.purpose)
    assert loaded[0].decision_payload["shared"]["current_price"] == "2510.00"
