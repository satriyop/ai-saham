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
        "src.adapters.cli.research_accum_evaluate_commands.resolve_compatibility_id",
        lambda repo, purpose, compatibility_id=None: "compat-test",
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteMarketRepository",
        lambda path: object(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.SQLiteCorporateActionCalendarRepository",
        lambda path: object(),
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
