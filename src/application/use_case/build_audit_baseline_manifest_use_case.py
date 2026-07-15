"""
Read-only audit baseline manifest builder (DQ-000).

Produces a reproducible snapshot of local database/config/code identity for
the audit harness. Never repairs, rebuilds, quarantines, or mutates data.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol


@dataclass(frozen=True)
class AuditDatabaseIdentity:
    path: str
    exists: bool
    sha256: str | None
    size_bytes: int | None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "exists": self.exists,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ConfigFileIdentity:
    path: str
    exists: bool
    sha256: str | None

    def to_dict(self) -> dict:
        return {"path": self.path, "exists": self.exists, "sha256": self.sha256}


@dataclass(frozen=True)
class AuditConfigIdentity:
    app_config_path: str
    user_config_path: str
    user_config_exists: bool
    config_files: tuple[ConfigFileIdentity, ...] = ()

    def to_dict(self) -> dict:
        return {
            "app_config_path": self.app_config_path,
            "user_config_path": self.user_config_path,
            "user_config_exists": self.user_config_exists,
            "config_files": [f.to_dict() for f in self.config_files],
        }


@dataclass(frozen=True)
class AuditCodeIdentity:
    git_commit: str | None
    git_dirty: bool
    git_status_short: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "git_status_short": list(self.git_status_short),
        }


@dataclass(frozen=True)
class AuditSchemaIdentity:
    sqlite_user_version: int | None
    migration_count: int | None
    tables: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "sqlite_user_version": self.sqlite_user_version,
            "migration_count": self.migration_count,
            "tables": list(self.tables),
        }


@dataclass(frozen=True)
class AuditTableSummary:
    table: str
    row_count: int
    min_date: str | None
    max_date: str | None
    ticker_count: int | None
    duplicate_key_count: int | None
    null_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "row_count": self.row_count,
            "min_date": self.min_date,
            "max_date": self.max_date,
            "ticker_count": self.ticker_count,
            "duplicate_key_count": self.duplicate_key_count,
            "null_summary": dict(self.null_summary),
        }


@dataclass(frozen=True)
class AuditValidationScope:
    tickers: tuple[str, ...]
    dates: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"tickers": list(self.tickers), "dates": list(self.dates)}


@dataclass(frozen=True)
class AuditBaselineManifest:
    artifact_type: str
    schema_version: int
    generated_at: str
    database: AuditDatabaseIdentity
    config: AuditConfigIdentity
    code: AuditCodeIdentity
    schema: AuditSchemaIdentity
    table_summaries: tuple[AuditTableSummary, ...]
    validation_scope: AuditValidationScope
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "database": self.database.to_dict(),
            "config": self.config.to_dict(),
            "code": self.code.to_dict(),
            "schema": self.schema.to_dict(),
            "table_summaries": [t.to_dict() for t in self.table_summaries],
            "validation_scope": self.validation_scope.to_dict(),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class BuildAuditBaselineManifestRequest:
    db_path: Path
    tickers: tuple[str, ...] = ()


class AuditManifestReader(Protocol):
    """Read-only local database identity/schema/table reader."""

    def database_identity(self) -> AuditDatabaseIdentity: ...

    def schema_identity(self) -> AuditSchemaIdentity: ...

    def table_summaries(self) -> tuple[AuditTableSummary, ...]: ...

    def warnings(self) -> tuple[str, ...]: ...


class AuditConfigReader(Protocol):
    """Read-only config file identity (paths + hashes)."""

    def config_identity(self) -> AuditConfigIdentity: ...

    def warnings(self) -> tuple[str, ...]: ...


class AuditCodeIdentityProvider(Protocol):
    """Read-only git/code identity."""

    def code_identity(self) -> AuditCodeIdentity: ...

    def warnings(self) -> tuple[str, ...]: ...


class AuditValidationPanelReader(Protocol):
    """Read-only validation panel fixture reader."""

    def validation_scope(self, tickers_override: tuple[str, ...]) -> AuditValidationScope: ...

    def warnings(self) -> tuple[str, ...]: ...


class BuildAuditBaselineManifestUseCase:
    """Assemble a deterministic read-only audit baseline manifest."""

    _ARTIFACT_TYPE = "audit_baseline_manifest"
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        manifest_reader: AuditManifestReader,
        config_reader: AuditConfigReader,
        code_identity_provider: AuditCodeIdentityProvider,
        validation_panel_reader: AuditValidationPanelReader,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._manifest_reader = manifest_reader
        self._config_reader = config_reader
        self._code_identity_provider = code_identity_provider
        self._validation_panel_reader = validation_panel_reader
        self._clock = clock or _default_clock

    def execute(self, request: BuildAuditBaselineManifestRequest) -> AuditBaselineManifest:
        warnings: list[str] = []

        database = self._manifest_reader.database_identity()
        schema = self._manifest_reader.schema_identity()
        table_summaries = self._manifest_reader.table_summaries()
        warnings.extend(self._manifest_reader.warnings())

        config = self._config_reader.config_identity()
        warnings.extend(self._config_reader.warnings())

        code = self._code_identity_provider.code_identity()
        warnings.extend(self._code_identity_provider.warnings())

        validation_scope = self._validation_panel_reader.validation_scope(request.tickers)
        warnings.extend(self._validation_panel_reader.warnings())

        return AuditBaselineManifest(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=self._clock(),
            database=database,
            config=config,
            code=code,
            schema=schema,
            table_summaries=table_summaries,
            validation_scope=validation_scope,
            warnings=tuple(warnings),
        )


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
