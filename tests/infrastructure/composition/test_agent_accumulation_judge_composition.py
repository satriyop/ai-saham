import hashlib
import sqlite3
from datetime import date

import pytest

from src.adapters.composition.screen_accum_request import (
    build_default_screen_accum_request,
)
from src.adapters.composition.screen_deps import ReadOnlyAccumulationJudgeRunner
from src.adapters.composition.stock_analysis_workflow_dependencies import (
    create_read_only_stock_analysis_workflow_dependencies,
)
from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import AgentToolExecutionStatus
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_accumulation_judge_tool import (
    AccumulationJudgeArguments,
    AccumulationJudgeTool,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.persistence.sqlite_setup_phase_ledger_repository import (
    SQLiteSetupPhaseLedgerReadRepository,
    SQLiteSetupPhaseLedgerRepository,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _identity(path) -> tuple[str, int, int]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path) as connection:
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
    return digest, schema_version, data_version


def test_read_only_ledger_reads_without_mutation_and_rejects_write(tmp_path) -> None:
    db_path = tmp_path / "agent-judge.db"
    SQLiteSetupPhaseLedgerRepository(db_path)
    before = _identity(db_path)
    repository = SQLiteSetupPhaseLedgerReadRepository(db_path)

    assert (
        repository.list_rows_before_many(
            tickers=["BBCA"],
            before_date=date(2026, 8, 3),
        )
        == ()
    )
    with pytest.raises(PermissionError, match="read-only"):
        repository.record_phase(
            ticker="BBCA",
            as_of_date=date(2026, 8, 2),
            phase=SetupPhaseState.ACCUMULATION,
            setup_family="foreign-bounce",
            source_workflow="screen_accum",
        )

    assert _identity(db_path) == before


def test_runner_uses_exact_shared_default_request_builder() -> None:
    captured = []

    class FakeWorkflow:
        def execute(self, request):
            captured.append(request)
            return object()

    runner = ReadOnlyAccumulationJudgeRunner(FakeWorkflow(), "lq45")

    assert runner("BBCA") is not None
    assert captured == [build_default_screen_accum_request(tickers=["BBCA"], universe="lq45")]


def test_read_only_dependency_bundle_has_no_api_learning_or_schema_seam(tmp_path) -> None:
    db_path = tmp_path / "agent-judge.db"
    SQLiteSetupPhaseLedgerRepository(db_path)
    before = _identity(db_path)

    dependencies = create_read_only_stock_analysis_workflow_dependencies(db_path)

    assert dependencies.learning_artifact_repository is None
    for name in dependencies.stockbit_providers.__slots__:
        provider = getattr(dependencies.stockbit_providers, name)
        assert provider._api_client is None
        assert provider._connection_provider.initialize_schema is False
    with pytest.raises(PermissionError, match="disabled"):
        dependencies.create_risk_engine()
    assert _identity(db_path) == before


def test_read_only_execution_attempt_cannot_mutate_database(tmp_path) -> None:
    from src.adapters.composition.screen_deps import (
        build_read_only_accumulation_judge_runner,
    )

    db_path = tmp_path / "agent-judge.db"
    SQLiteSetupPhaseLedgerRepository(db_path)
    before = _identity(db_path)
    runner = build_read_only_accumulation_judge_runner(db_path, universe="lq45")
    use_case = runner.use_case

    assert use_case._save_watchlist_use_case is None
    assert use_case._evaluate_market_context is None
    assert use_case._collect_diagnostic_evidence is None
    assert use_case._screen_use_case._candidate_observations_repo is None
    assert use_case._screen_use_case._record_setup_phase is False
    assert isinstance(
        use_case._screen_use_case._setup_phase_history_repo,
        SQLiteSetupPhaseLedgerReadRepository,
    )

    result = AccumulationJudgeTool(runner).execute(
        "judge-read-only",
        AccumulationJudgeArguments("BBCA"),
        AgentToolExecutionContext(build_agent_accumulation_context(make_candidate())),
    )

    assert result.status in {
        AgentToolExecutionStatus.FAILED,
        AgentToolExecutionStatus.UNAVAILABLE,
    }
    assert _identity(db_path) == before
