"""CLI: research accum labels --all-label-contracts."""

from __future__ import annotations

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.application.use_case.database_learning_lifecycle_use_case import (
    ACCUM_PATH_LABEL_CONTRACTS,
    GenerateLearningLabelsResult,
)
from src.domain.value_objects.learning_artifacts import LearningContractId

runner = CliRunner()


def test_all_label_contracts_runs_each_accum_path_contract(monkeypatch) -> None:
    seen: list[LearningContractId] = []

    class _FakeUC:
        def __init__(self, **kwargs):
            pass

        def execute(self, request):
            seen.append(request.label_contract)
            return GenerateLearningLabelsResult(
                observation_count=0,
                inserted_count=0,
                idempotent_count=0,
                unavailable_count=0,
                skipped_count=0,
                labels=(),
            )

    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.GenerateAccumulationPricePathLabelsUseCase",
        _FakeUC,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.repository",
        lambda db_path=None: (None, object()),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.resolve_label_compatibility_ids",
        lambda repo, purpose, compatibility_id=None: ["compat-test"],
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteMarketRepository",
        lambda path: object(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteCorporateActionCalendarRepository",
        lambda path: object(),
    )

    class _EmptySnapStore:
        def list_snapshots(self):
            return ()

    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteTradingSessionCalendarSnapshotRepository",
        lambda path: _EmptySnapStore(),
    )

    result = runner.invoke(
        app,
        ["research", "accum", "labels", "--all-label-contracts", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert seen == list(ACCUM_PATH_LABEL_CONTRACTS)
    assert "learning_label_generation_batch" in result.output
    assert "price_path.accum_3d.v1" in result.output
    assert "price_path.accum_10d.v1" in result.output
    assert "price_path.accum_20d.v1" in result.output


def test_all_label_contracts_rejects_with_explicit_label_contract() -> None:
    result = runner.invoke(
        app,
        [
            "research",
            "accum",
            "labels",
            "--all-label-contracts",
            "--label-contract",
            "price_path.accum_10d.v1",
        ],
    )
    assert result.exit_code != 0
    assert "either --all-label-contracts or --label-contract" in result.output


def test_labels_all_compatibility_cohorts_independently(monkeypatch) -> None:
    """Cron omits --compatibility-id; multi-cohort must not fail-closed."""
    seen_cohorts: list[str] = []
    seen_contracts: list[LearningContractId] = []

    class _FakeUC:
        def __init__(self, **kwargs):
            pass

        def execute(self, request):
            seen_cohorts.append(request.compatibility_id)
            seen_contracts.append(request.label_contract)
            return GenerateLearningLabelsResult(
                observation_count=1,
                inserted_count=1,
                idempotent_count=0,
                unavailable_count=0,
                skipped_count=0,
                labels=(),
            )

    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.GenerateAccumulationPricePathLabelsUseCase",
        _FakeUC,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.repository",
        lambda db_path=None: (None, object()),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.resolve_label_compatibility_ids",
        lambda repo, purpose, compatibility_id=None: ["cohort-old", "cohort-new"],
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteMarketRepository",
        lambda path: object(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteCorporateActionCalendarRepository",
        lambda path: object(),
    )

    class _EmptySnapStore:
        def list_snapshots(self):
            return ()

    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteTradingSessionCalendarSnapshotRepository",
        lambda path: _EmptySnapStore(),
    )

    result = runner.invoke(
        app,
        ["research", "accum", "labels", "--all-label-contracts", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert "learning_label_generation_multi_cohort" in result.output
    assert "cohort-old" in result.output
    assert "cohort-new" in result.output
    # each cohort × each path contract
    assert seen_cohorts.count("cohort-old") == len(ACCUM_PATH_LABEL_CONTRACTS)
    assert seen_cohorts.count("cohort-new") == len(ACCUM_PATH_LABEL_CONTRACTS)
    assert len(seen_contracts) == 2 * len(ACCUM_PATH_LABEL_CONTRACTS)


def test_resolve_label_compatibility_ids_lists_all() -> None:
    from types import SimpleNamespace

    import pytest
    import typer

    from src.adapters.cli.research_learning_helpers import (
        resolve_compatibility_id,
        resolve_label_compatibility_ids,
    )
    from src.domain.value_objects.learning_artifacts import AssessmentPurpose

    class _Repo:
        def list_observations(self, purpose):
            return [
                SimpleNamespace(compatibility_id="sha256:a"),
                SimpleNamespace(compatibility_id="sha256:b"),
                SimpleNamespace(compatibility_id="sha256:a"),
            ]

    repo = _Repo()
    purpose = AssessmentPurpose.ACCUMULATION_DISCOVERY
    assert resolve_label_compatibility_ids(repo, purpose, None) == [
        "sha256:a",
        "sha256:b",
    ]
    assert resolve_label_compatibility_ids(repo, purpose, "sha256:b") == ["sha256:b"]
    # evaluate path still fail-closed
    with pytest.raises(typer.BadParameter, match="specify --compatibility-id"):
        resolve_compatibility_id(repo, purpose, None)
