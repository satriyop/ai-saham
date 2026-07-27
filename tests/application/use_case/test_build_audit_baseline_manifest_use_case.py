"""Tests for BuildAuditBaselineManifestUseCase (DQ-000)."""

from __future__ import annotations

from pathlib import Path

from src.application.use_case.build_audit_baseline_manifest_use_case import (
    AuditBaselineManifest,
    AuditCodeIdentity,
    AuditConfigIdentity,
    AuditDatabaseIdentity,
    AuditSchemaIdentity,
    AuditTableSummary,
    AuditValidationScope,
    BuildAuditBaselineManifestRequest,
    BuildAuditBaselineManifestUseCase,
)


class _FakeManifestReader:
    def __init__(self, database_exists: bool = True) -> None:
        self._database_exists = database_exists
        self._warnings = () if database_exists else ("database_missing",)

    def database_identity(self) -> AuditDatabaseIdentity:
        if not self._database_exists:
            return AuditDatabaseIdentity(
                path="missing.db", exists=False, sha256=None, size_bytes=None
            )
        return AuditDatabaseIdentity(path="data.db", exists=True, sha256="abc123", size_bytes=1024)

    def schema_identity(self) -> AuditSchemaIdentity:
        if not self._database_exists:
            return AuditSchemaIdentity(sqlite_user_version=None, migration_count=None, tables=())
        return AuditSchemaIdentity(sqlite_user_version=0, migration_count=5, tables=("candles",))

    def table_summaries(self) -> tuple[AuditTableSummary, ...]:
        if not self._database_exists:
            return ()
        return (
            AuditTableSummary(
                table="candles",
                row_count=100,
                min_date="2026-01-01",
                max_date="2026-01-31",
                ticker_count=10,
                duplicate_key_count=0,
                null_summary={"ticker": 0, "date": 0},
            ),
        )

    def warnings(self) -> tuple[str, ...]:
        return self._warnings


class _FakeConfigReader:
    def config_identity(self) -> AuditConfigIdentity:
        return AuditConfigIdentity(
            app_config_path="config/default.yaml",
            user_config_path="config/user.yaml",
            user_config_exists=False,
            config_files=(),
        )

    def warnings(self) -> tuple[str, ...]:
        return ()


class _FakeCodeIdentityProvider:
    def __init__(self, available: bool = True) -> None:
        self._available = available

    def code_identity(self) -> AuditCodeIdentity:
        if not self._available:
            return AuditCodeIdentity(git_commit=None, git_dirty=False, git_status_short=())
        return AuditCodeIdentity(
            git_commit="deadbeef", git_dirty=True, git_status_short=(" M file.py",)
        )

    def warnings(self) -> tuple[str, ...]:
        return () if self._available else ("git_unavailable",)


class _FakeValidationPanelReader:
    def validation_scope(self, tickers_override: tuple[str, ...]) -> AuditValidationScope:
        tickers = tickers_override or ("BBCA", "BBRI")
        return AuditValidationScope(tickers=tickers, dates=("2026-01-02",))

    def warnings(self) -> tuple[str, ...]:
        return ()


def _fixed_clock() -> str:
    return "2026-07-16T00:00:00+00:00"


def test_execute_returns_complete_manifest_with_expected_shape():
    use_case = BuildAuditBaselineManifestUseCase(
        manifest_reader=_FakeManifestReader(),
        config_reader=_FakeConfigReader(),
        code_identity_provider=_FakeCodeIdentityProvider(),
        validation_panel_reader=_FakeValidationPanelReader(),
        clock=_fixed_clock,
    )

    manifest = use_case.execute(
        BuildAuditBaselineManifestRequest(db_path=Path("data.db"), tickers=())
    )

    assert isinstance(manifest, AuditBaselineManifest)
    assert manifest.artifact_type == "audit_baseline_manifest"
    assert manifest.schema_version == 1
    assert manifest.generated_at == "2026-07-16T00:00:00+00:00"
    assert manifest.database.exists is True
    assert manifest.database.sha256 == "abc123"
    assert manifest.schema.tables == ("candles",)
    assert len(manifest.table_summaries) == 1
    assert manifest.table_summaries[0].table == "candles"
    assert manifest.code.git_commit == "deadbeef"
    assert manifest.validation_scope.tickers == ("BBCA", "BBRI")
    assert manifest.warnings == ()


def test_execute_merges_warnings_from_all_readers():
    use_case = BuildAuditBaselineManifestUseCase(
        manifest_reader=_FakeManifestReader(database_exists=False),
        config_reader=_FakeConfigReader(),
        code_identity_provider=_FakeCodeIdentityProvider(available=False),
        validation_panel_reader=_FakeValidationPanelReader(),
        clock=_fixed_clock,
    )

    manifest = use_case.execute(BuildAuditBaselineManifestRequest(db_path=Path("missing.db")))

    assert manifest.database.exists is False
    assert manifest.database.sha256 is None
    assert manifest.table_summaries == ()
    assert "database_missing" in manifest.warnings
    assert "git_unavailable" in manifest.warnings


def test_missing_database_does_not_crash_use_case():
    use_case = BuildAuditBaselineManifestUseCase(
        manifest_reader=_FakeManifestReader(database_exists=False),
        config_reader=_FakeConfigReader(),
        code_identity_provider=_FakeCodeIdentityProvider(),
        validation_panel_reader=_FakeValidationPanelReader(),
        clock=_fixed_clock,
    )

    manifest = use_case.execute(BuildAuditBaselineManifestRequest(db_path=Path("missing.db")))

    assert manifest.database.exists is False
    assert manifest.schema.sqlite_user_version is None


def test_manifest_to_dict_includes_required_top_level_keys():
    use_case = BuildAuditBaselineManifestUseCase(
        manifest_reader=_FakeManifestReader(),
        config_reader=_FakeConfigReader(),
        code_identity_provider=_FakeCodeIdentityProvider(),
        validation_panel_reader=_FakeValidationPanelReader(),
        clock=_fixed_clock,
    )

    manifest = use_case.execute(BuildAuditBaselineManifestRequest(db_path=Path("data.db")))
    payload = manifest.to_dict()

    for key in (
        "artifact_type",
        "schema_version",
        "generated_at",
        "database",
        "config",
        "code",
        "schema",
        "table_summaries",
        "validation_scope",
        "warnings",
    ):
        assert key in payload

    assert payload["artifact_type"] == "audit_baseline_manifest"
    assert payload["schema_version"] == 1
    assert payload["table_summaries"][0]["table"] == "candles"


def test_ticker_override_takes_precedence_over_panel_defaults():
    use_case = BuildAuditBaselineManifestUseCase(
        manifest_reader=_FakeManifestReader(),
        config_reader=_FakeConfigReader(),
        code_identity_provider=_FakeCodeIdentityProvider(),
        validation_panel_reader=_FakeValidationPanelReader(),
        clock=_fixed_clock,
    )

    manifest = use_case.execute(
        BuildAuditBaselineManifestRequest(db_path=Path("data.db"), tickers=("TLKM",))
    )

    assert manifest.validation_scope.tickers == ("TLKM",)
