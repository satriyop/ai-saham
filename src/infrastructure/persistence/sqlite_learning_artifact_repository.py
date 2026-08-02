"""SQLite implementation of the database-owned learning artifact ports."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar

from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    EvaluationMethod,
    EvaluationReadiness,
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningEvaluation,
    LearningObservation,
    LearningOutcomeLabel,
    LearningPolicyApplication,
    LearningPolicyProposal,
    LearningPolicyValidation,
    LearningTrackSnapshot,
    OutcomeBasis,
    ProductionPolicySnapshot,
    ValidationStatus,
    canonical_json,
    stable_learning_id,
    validate_artifact_integrity,
    validate_policy_snapshot_integrity,
)

# Label contracts whose identity is discoverable from a parent observation_id.
_LABEL_DISCOVERY_CONTRACTS: tuple[LearningContractId, ...] = (
    LearningContractId.ACCUM_3D_LABEL,
    LearningContractId.ACCUM_10D_LABEL,
    LearningContractId.ACCUM_20D_LABEL,
    LearningContractId.PRE_OPEN_LABEL,
)

LEARNING_MIGRATION_NAMESPACE = "database_owned_learning"

LEARNING_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS learning_observations (
        observation_id TEXT PRIMARY KEY,
        artifact_digest TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        contract_id TEXT NOT NULL,
        purpose TEXT NOT NULL CHECK (purpose IN (
            'ACCUMULATION_DISCOVERY',
            'PRE_OPEN_AUCTION_DIRECTION',
            'SWING_TRADE_SETUP'
        )),
        policy_contract TEXT NOT NULL,
        horizon_contract TEXT NOT NULL,
        compatibility_id TEXT NOT NULL,
        cutoff_at TEXT NOT NULL,
        universe_id TEXT NOT NULL,
        window_id TEXT NOT NULL,
        decision_payload_json TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        artifact_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_observations_purpose_compatibility
    ON learning_observations(purpose, compatibility_id, cutoff_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_track_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        artifact_digest TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        observation_id TEXT NOT NULL,
        sampled_at TEXT NOT NULL,
        source TEXT NOT NULL,
        snapshot_payload_json TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        artifact_json TEXT NOT NULL,
        FOREIGN KEY (observation_id) REFERENCES learning_observations(observation_id)
            ON DELETE RESTRICT,
        UNIQUE (observation_id, sampled_at, source)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_tracks_observation_sample
    ON learning_track_snapshots(observation_id, sampled_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_outcome_labels (
        label_id TEXT PRIMARY KEY,
        artifact_digest TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        contract_id TEXT NOT NULL,
        observation_id TEXT NOT NULL,
        outcome_basis TEXT NOT NULL CHECK (outcome_basis IN (
            'PRICE_PATH_ONLY',
            'SIMULATED_NET_EXECUTION',
            'REALIZED_TRADE'
        )),
        availability TEXT NOT NULL CHECK (availability IN ('AVAILABLE', 'UNAVAILABLE')),
        outcome TEXT,
        metrics_json TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        labeled_at TEXT NOT NULL,
        artifact_json TEXT NOT NULL,
        FOREIGN KEY (observation_id) REFERENCES learning_observations(observation_id)
            ON DELETE RESTRICT,
        UNIQUE (observation_id, contract_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_labels_observation
    ON learning_outcome_labels(observation_id, contract_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_evaluations (
        evaluation_id TEXT PRIMARY KEY,
        artifact_digest TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        contract_id TEXT NOT NULL,
        purpose TEXT NOT NULL,
        evaluation_method TEXT NOT NULL,
        compatibility_id TEXT NOT NULL,
        dataset_fingerprint TEXT NOT NULL,
        split_contract TEXT NOT NULL,
        population_json TEXT NOT NULL,
        exclusions_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        outcome_basis TEXT NOT NULL,
        readiness TEXT NOT NULL CHECK (readiness IN (
            'INELIGIBLE',
            'DESCRIPTIVE_READY',
            'OOS_DIAGNOSTIC_READY',
            'POLICY_REVIEW_ELIGIBLE'
        )),
        evaluated_at TEXT NOT NULL,
        artifact_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_evaluations_purpose_method
    ON learning_evaluations(purpose, evaluation_method, evaluated_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_policy_proposals (
        proposal_id TEXT PRIMARY KEY,
        artifact_digest TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        contract_id TEXT NOT NULL,
        source_evaluation_id TEXT NOT NULL,
        current_config_hash TEXT NOT NULL,
        changes_json TEXT NOT NULL,
        rationale_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        artifact_json TEXT NOT NULL,
        FOREIGN KEY (source_evaluation_id) REFERENCES learning_evaluations(evaluation_id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_policy_validations (
        validation_id TEXT PRIMARY KEY,
        artifact_digest TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        contract_id TEXT NOT NULL,
        proposal_id TEXT NOT NULL UNIQUE,
        baseline_evaluation_id TEXT NOT NULL,
        proposed_evaluation_id TEXT NOT NULL,
        population_fingerprint TEXT NOT NULL,
        paired_deltas_json TEXT NOT NULL,
        issues_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL')),
        validated_at TEXT NOT NULL,
        artifact_json TEXT NOT NULL,
        FOREIGN KEY (proposal_id) REFERENCES learning_policy_proposals(proposal_id)
            ON DELETE RESTRICT,
        FOREIGN KEY (baseline_evaluation_id) REFERENCES learning_evaluations(evaluation_id)
            ON DELETE RESTRICT,
        FOREIGN KEY (proposed_evaluation_id) REFERENCES learning_evaluations(evaluation_id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_policy_applications (
        application_id TEXT PRIMARY KEY,
        artifact_digest TEXT NOT NULL,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        contract_id TEXT NOT NULL,
        proposal_id TEXT NOT NULL UNIQUE,
        validation_id TEXT NOT NULL UNIQUE,
        previous_config_hash TEXT NOT NULL,
        applied_config_hash TEXT NOT NULL,
        exact_changes_json TEXT NOT NULL,
        confirmation_identity TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        reread_verified INTEGER NOT NULL CHECK (reread_verified = 1),
        artifact_json TEXT NOT NULL,
        FOREIGN KEY (proposal_id) REFERENCES learning_policy_proposals(proposal_id)
            ON DELETE RESTRICT,
        FOREIGN KEY (validation_id) REFERENCES learning_policy_validations(validation_id)
            ON DELETE RESTRICT
    )
    """,
    # ADR-059: cohort-bound production policy snapshots (v1 historical + v2 active).
    """
    CREATE TABLE IF NOT EXISTS learning_policy_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        contract_id TEXT NOT NULL CHECK (
            contract_id IN (
                'production_policy_snapshot.v1',
                'production_policy_snapshot.v2'
            )
        ),
        purpose TEXT NOT NULL,
        learning_observation_contract_id TEXT NOT NULL,
        producer_observation_contract TEXT NOT NULL,
        compatibility_id TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        decision_type TEXT NOT NULL,
        semantic_engine_contract_id TEXT NOT NULL,
        material_config_hash TEXT NOT NULL,
        canonical_payload_json TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        source_revision TEXT NOT NULL,
        created_at TEXT NOT NULL,
        artifact_json TEXT NOT NULL,
        UNIQUE (purpose, compatibility_id, policy_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_policy_snapshots_cohort
    ON learning_policy_snapshots(purpose, compatibility_id, policy_id)
    """,
)

_POLICY_SNAPSHOT_COLUMNS: tuple[str, ...] = (
    "snapshot_id",
    "schema_version",
    "contract_id",
    "purpose",
    "learning_observation_contract_id",
    "producer_observation_contract",
    "compatibility_id",
    "policy_id",
    "policy_version",
    "decision_type",
    "semantic_engine_contract_id",
    "material_config_hash",
    "canonical_payload_json",
    "payload_digest",
    "source_revision",
    "created_at",
    "artifact_json",
)

_POLICY_SNAPSHOT_CREATE_V3 = """
CREATE TABLE learning_policy_snapshots__v3 (
    snapshot_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    contract_id TEXT NOT NULL CHECK (
        contract_id IN (
            'production_policy_snapshot.v1',
            'production_policy_snapshot.v2'
        )
    ),
    purpose TEXT NOT NULL,
    learning_observation_contract_id TEXT NOT NULL,
    producer_observation_contract TEXT NOT NULL,
    compatibility_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    semantic_engine_contract_id TEXT NOT NULL,
    material_config_hash TEXT NOT NULL,
    canonical_payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    created_at TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    UNIQUE (purpose, compatibility_id, policy_id)
)
"""

Artifact = TypeVar("Artifact")


def connect_learning_database(db_path: Path) -> sqlite3.Connection:
    """Open a learning repository connection with mandatory FK enforcement."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        connection.close()
        raise LearningContractError("SQLite foreign key enforcement is required")
    return connection


def _applied_learning_migration_versions(connection: sqlite3.Connection) -> set[int]:
    rows = connection.execute(
        "SELECT version FROM _schema_migrations WHERE namespace = ?",
        (LEARNING_MIGRATION_NAMESPACE,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _migrate_learning_policy_snapshots_v3(connection: sqlite3.Connection) -> None:
    """Rebuild learning_policy_snapshots to accept production_policy_snapshot.v2.

    Existing databases stamped migration 2 with a v1-only CHECK cannot accept
    v2 rows until the table is rebuilt. Fresh DBs already CREATE with the
    widened CHECK; this still runs a no-content-loss rebuild when version 3 is
    missing and the table exists.
    """

    if not _table_exists(connection, "learning_policy_snapshots"):
        # CREATE IF NOT EXISTS from LEARNING_SCHEMA_STATEMENTS already applied.
        return

    col_list = ", ".join(_POLICY_SNAPSHOT_COLUMNS)
    before_rows = connection.execute(
        f"SELECT {col_list} FROM learning_policy_snapshots ORDER BY snapshot_id"  # noqa: S608
    ).fetchall()
    before_count = len(before_rows)
    before_pairs = [(row["snapshot_id"], row["payload_digest"]) for row in before_rows]

    connection.execute("DROP TABLE IF EXISTS learning_policy_snapshots__v3")
    connection.execute(_POLICY_SNAPSHOT_CREATE_V3)
    if before_count:
        connection.execute(
            f"INSERT INTO learning_policy_snapshots__v3 ({col_list}) "  # noqa: S608
            f"SELECT {col_list} FROM learning_policy_snapshots"
        )
    after_count = connection.execute(
        "SELECT COUNT(*) AS n FROM learning_policy_snapshots__v3"
    ).fetchone()["n"]
    if int(after_count) != before_count:
        raise LearningContractError(
            "learning_policy_snapshots v3 migration row count mismatch: "
            f"before={before_count} after={after_count}"
        )
    after_pairs = [
        (row["snapshot_id"], row["payload_digest"])
        for row in connection.execute(
            "SELECT snapshot_id, payload_digest FROM learning_policy_snapshots__v3 "
            "ORDER BY snapshot_id"
        ).fetchall()
    ]
    if after_pairs != before_pairs:
        raise LearningContractError(
            "learning_policy_snapshots v3 migration content mismatch (snapshot_id, payload_digest)"
        )

    connection.execute("DROP TABLE learning_policy_snapshots")
    connection.execute(
        "ALTER TABLE learning_policy_snapshots__v3 RENAME TO learning_policy_snapshots"
    )
    connection.execute("DROP INDEX IF EXISTS idx_learning_policy_snapshots_cohort")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_policy_snapshots_cohort
        ON learning_policy_snapshots(purpose, compatibility_id, policy_id)
        """
    )
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise LearningContractError(
            f"learning_policy_snapshots v3 migration foreign_key_check failed: {violations!r}"
        )


def create_learning_schema(connection: sqlite3.Connection) -> None:
    """Create the canonical learning tables and their indexes.

    Statements use CREATE IF NOT EXISTS so additive tables (e.g. ADR-059
    ``learning_policy_snapshots``) apply on existing databases that already
    recorded migration version 1. Migration version 3 rebuilds the snapshots
    table CHECK to accept production_policy_snapshot.v2.
    """

    connection.execute("""
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            namespace TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (namespace, version)
        )
        """)
    for statement in LEARNING_SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        """
        INSERT OR IGNORE INTO _schema_migrations(namespace, version)
        VALUES (?, 1)
        """,
        (LEARNING_MIGRATION_NAMESPACE,),
    )
    # Version 2: production policy snapshots (ADR-059). Idempotent CREATE above.
    connection.execute(
        """
        INSERT OR IGNORE INTO _schema_migrations(namespace, version)
        VALUES (?, 2)
        """,
        (LEARNING_MIGRATION_NAMESPACE,),
    )
    applied = _applied_learning_migration_versions(connection)
    if 3 not in applied:
        # Real rebuild required for DBs that still have the v1-only CHECK.
        _migrate_learning_policy_snapshots_v3(connection)
        connection.execute(
            """
            INSERT OR IGNORE INTO _schema_migrations(namespace, version)
            VALUES (?, 3)
            """,
            (LEARNING_MIGRATION_NAMESPACE,),
        )


def ensure_learning_schema(db_path: Path) -> None:
    with connect_learning_database(db_path) as connection:
        create_learning_schema(connection)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise LearningContractError("learning schema has foreign key violations")


def _artifact_json(artifact: Any) -> str:
    return canonical_json(asdict(artifact))


class LearningArtifactReadIntegrityError(LearningContractError):
    """Normalized SQLite columns disagree with authoritative artifact_json."""


_OBS_COLUMNS: tuple[str, ...] = (
    "observation_id",
    "artifact_digest",
    "schema_version",
    "contract_id",
    "purpose",
    "policy_contract",
    "horizon_contract",
    "compatibility_id",
    "cutoff_at",
    "universe_id",
    "window_id",
    "decision_payload_json",
    "captured_at",
    "artifact_json",
)
_OBS_SELECT = ", ".join(_OBS_COLUMNS)

_LABEL_COLUMNS: tuple[str, ...] = (
    "label_id",
    "artifact_digest",
    "schema_version",
    "contract_id",
    "observation_id",
    "outcome_basis",
    "availability",
    "outcome",
    "metrics_json",
    "fingerprint",
    "labeled_at",
    "artifact_json",
)
_LABEL_SELECT = ", ".join(_LABEL_COLUMNS)

_POLICY_SELECT = ", ".join(_POLICY_SNAPSHOT_COLUMNS)


def _cell_equal(actual: Any, expected: Any) -> bool:
    """Strict equality for normalized shadow columns (no silent string coercion)."""
    if actual is None and expected is None:
        return True
    if type(actual) is int and type(expected) is int:
        return actual == expected
    # SQLite may surface integers as int while writers store same value.
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if type(actual) is bool or type(expected) is bool:
            return actual is expected
        return actual == expected
    return actual == expected


def _assert_row_matches_expected(
    row: sqlite3.Row,
    expected: Mapping[str, Any],
    *,
    table: str,
    artifact_id: str,
) -> None:
    for name, want in expected.items():
        got = row[name]
        if not _cell_equal(got, want):
            raise LearningArtifactReadIntegrityError(
                f"learning row integrity error: {table}.{artifact_id} "
                f"column {name!r} disagrees with artifact_json "
                f"(column={got!r}, artifact={want!r})"
            )


def _observation_expected_columns(obs: LearningObservation) -> dict[str, Any]:
    return {
        "observation_id": obs.observation_id,
        "artifact_digest": obs.artifact_digest,
        "schema_version": obs.schema_version,
        "contract_id": obs.contract_id.value,
        "purpose": obs.purpose.value,
        "policy_contract": obs.policy_contract,
        "horizon_contract": obs.horizon_contract,
        "compatibility_id": obs.compatibility_id,
        "cutoff_at": obs.cutoff_at.isoformat(),
        "universe_id": obs.universe_id,
        "window_id": obs.window_id,
        "decision_payload_json": canonical_json(obs.decision_payload),
        "captured_at": obs.captured_at.isoformat(),
        "artifact_json": _artifact_json(obs),
    }


def _label_expected_columns(label: LearningOutcomeLabel) -> dict[str, Any]:
    return {
        "label_id": label.label_id,
        "artifact_digest": label.artifact_digest,
        "schema_version": label.schema_version,
        "contract_id": label.contract_id.value,
        "observation_id": label.observation_id,
        "outcome_basis": label.outcome_basis.value,
        "availability": label.availability.value,
        "outcome": label.outcome,
        "metrics_json": canonical_json(label.metrics),
        "fingerprint": label.fingerprint,
        "labeled_at": label.labeled_at.isoformat(),
        "artifact_json": _artifact_json(label),
    }


def _policy_expected_columns(snap: ProductionPolicySnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": snap.snapshot_id,
        "schema_version": snap.schema_version,
        "contract_id": snap.contract_id.value,
        "purpose": snap.purpose.value,
        "learning_observation_contract_id": snap.learning_observation_contract_id,
        "producer_observation_contract": snap.producer_observation_contract,
        "compatibility_id": snap.compatibility_id,
        "policy_id": snap.policy_id,
        "policy_version": snap.policy_version,
        "decision_type": snap.decision_type,
        "semantic_engine_contract_id": snap.semantic_engine_contract_id,
        "material_config_hash": snap.material_config_hash,
        "canonical_payload_json": canonical_json(snap.canonical_payload),
        "payload_digest": snap.payload_digest,
        "source_revision": snap.source_revision,
        "created_at": snap.created_at.isoformat(),
        "artifact_json": _artifact_json(snap),
    }


def _immutable_insert(
    connection: sqlite3.Connection,
    *,
    table: str,
    id_column: str,
    artifact_id: str,
    digest: str,
    insert_sql: str,
    values: tuple[Any, ...],
    digest_column: str = "artifact_digest",
    column_names: Sequence[str] | None = None,
) -> bool:
    existing = connection.execute(
        f"SELECT * FROM {table} WHERE {id_column} = ?",  # noqa: S608
        (artifact_id,),
    ).fetchone()
    if existing is not None:
        if existing[digest_column] != digest:
            raise LearningContractError(f"immutable artifact conflict for {table}.{artifact_id}")
        # Matching digest alone is not enough: corrupted shadow columns must fail.
        if column_names is not None:
            if len(column_names) != len(values):
                raise LearningContractError(
                    f"immutable insert column/value arity mismatch for {table}.{artifact_id}"
                )
            expected = dict(zip(column_names, values, strict=True))
            _assert_row_matches_expected(existing, expected, table=table, artifact_id=artifact_id)
        return False
    connection.execute(insert_sql, values)
    return True


def _load_observation_row(row: sqlite3.Row) -> LearningObservation:
    try:
        raw = json.loads(row["artifact_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise LearningArtifactReadIntegrityError(
            f"learning observation artifact_json corrupt: {exc}"
        ) from exc
    obs = _observation_from_dict(raw)
    _assert_row_matches_expected(
        row,
        _observation_expected_columns(obs),
        table="learning_observations",
        artifact_id=str(row["observation_id"]),
    )
    return obs


def _load_label_row(row: sqlite3.Row) -> LearningOutcomeLabel:
    try:
        raw = json.loads(row["artifact_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise LearningArtifactReadIntegrityError(
            f"learning label artifact_json corrupt: {exc}"
        ) from exc
    label = _label_from_dict(raw)
    _assert_row_matches_expected(
        row,
        _label_expected_columns(label),
        table="learning_outcome_labels",
        artifact_id=str(row["label_id"]),
    )
    return label


def _load_policy_row(row: sqlite3.Row) -> ProductionPolicySnapshot:
    try:
        raw = json.loads(row["artifact_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise LearningArtifactReadIntegrityError(
            f"learning policy snapshot artifact_json corrupt: {exc}"
        ) from exc
    snap = _policy_snapshot_from_dict(raw)
    _assert_row_matches_expected(
        row,
        _policy_expected_columns(snap),
        table="learning_policy_snapshots",
        artifact_id=str(row["snapshot_id"]),
    )
    return snap


def _load_json(row: sqlite3.Row, loader: Callable[[dict[str, Any]], Artifact]) -> Artifact:
    """Legacy loader for artifact types without column reconciliation yet."""
    return loader(json.loads(row["artifact_json"]))


def _observation_from_dict(data: dict[str, Any]) -> LearningObservation:
    return LearningObservation(
        **{
            **data,
            "contract_id": LearningContractId(data["contract_id"]),
            "purpose": AssessmentPurpose(data["purpose"]),
            "cutoff_at": datetime.fromisoformat(data["cutoff_at"]),
            "captured_at": datetime.fromisoformat(data["captured_at"]),
        }
    )


def _track_from_dict(data: dict[str, Any]) -> LearningTrackSnapshot:
    return LearningTrackSnapshot(
        **{
            **data,
            "sampled_at": datetime.fromisoformat(data["sampled_at"]),
            "captured_at": datetime.fromisoformat(data["captured_at"]),
        }
    )


def _label_from_dict(data: dict[str, Any]) -> LearningOutcomeLabel:
    return LearningOutcomeLabel(
        **{
            **data,
            "contract_id": LearningContractId(data["contract_id"]),
            "outcome_basis": OutcomeBasis(data["outcome_basis"]),
            "availability": LabelAvailability(data["availability"]),
            "labeled_at": datetime.fromisoformat(data["labeled_at"]),
        }
    )


def _evaluation_from_dict(data: dict[str, Any]) -> LearningEvaluation:
    return LearningEvaluation(
        **{
            **data,
            "contract_id": LearningContractId(data["contract_id"]),
            "purpose": AssessmentPurpose(data["purpose"]),
            "method": EvaluationMethod(data["method"]),
            "outcome_basis": OutcomeBasis(data["outcome_basis"]),
            "readiness": EvaluationReadiness(data["readiness"]),
            "evaluated_at": datetime.fromisoformat(data["evaluated_at"]),
        }
    )


def _proposal_from_dict(data: dict[str, Any]) -> LearningPolicyProposal:
    return LearningPolicyProposal(
        **{
            **data,
            "contract_id": LearningContractId(data["contract_id"]),
            "created_at": datetime.fromisoformat(data["created_at"]),
        }
    )


def _validation_from_dict(data: dict[str, Any]) -> LearningPolicyValidation:
    return LearningPolicyValidation(
        **{
            **data,
            "contract_id": LearningContractId(data["contract_id"]),
            "issues": tuple(data["issues"]),
            "status": ValidationStatus(data["status"]),
            "validated_at": datetime.fromisoformat(data["validated_at"]),
        }
    )


def _application_from_dict(data: dict[str, Any]) -> LearningPolicyApplication:
    return LearningPolicyApplication(
        **{
            **data,
            "contract_id": LearningContractId(data["contract_id"]),
            "applied_at": datetime.fromisoformat(data["applied_at"]),
        }
    )


def _policy_snapshot_from_dict(data: dict[str, Any]) -> ProductionPolicySnapshot:
    return ProductionPolicySnapshot(
        **{
            **data,
            "contract_id": LearningContractId(data["contract_id"]),
            "purpose": AssessmentPurpose(data["purpose"]),
            "created_at": datetime.fromisoformat(data["created_at"]),
        }
    )


class SQLiteLearningArtifactRepository:
    """One transaction-safe implementation shared by the learning ports."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        ensure_learning_schema(self._db_path)

    def _connect(self) -> sqlite3.Connection:
        return connect_learning_database(self._db_path)

    def add_observation(self, artifact: LearningObservation) -> bool:
        validate_artifact_integrity(artifact, id_field="observation_id")
        values = (
            artifact.observation_id,
            artifact.artifact_digest,
            artifact.schema_version,
            artifact.contract_id.value,
            artifact.purpose.value,
            artifact.policy_contract,
            artifact.horizon_contract,
            artifact.compatibility_id,
            artifact.cutoff_at.isoformat(),
            artifact.universe_id,
            artifact.window_id,
            canonical_json(artifact.decision_payload),
            artifact.captured_at.isoformat(),
            _artifact_json(artifact),
        )
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_observations",
                id_column="observation_id",
                artifact_id=artifact.observation_id,
                digest=artifact.artifact_digest,
                insert_sql="""
                    INSERT INTO learning_observations VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """,
                values=values,
                column_names=_OBS_COLUMNS,
            )

    def get_observation(self, observation_id: str) -> LearningObservation | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_OBS_SELECT} FROM learning_observations "
                "WHERE observation_id = ? OR json_extract(artifact_json, '$.observation_id') = ?",
                (observation_id, observation_id),
            ).fetchone()
        return None if row is None else _load_observation_row(row)

    def list_observations(
        self, purpose: AssessmentPurpose, *, compatibility_id: str | None = None
    ) -> Sequence[LearningObservation]:
        # Dual-key visibility: corrupt normalized lookup columns cannot hide rows.
        # Parentheses required: AND binds tighter than OR.
        sql = (
            f"SELECT {_OBS_SELECT} FROM learning_observations "
            "WHERE (purpose = ? OR json_extract(artifact_json, '$.purpose') = ?)"
        )
        values: list[str] = [purpose.value, purpose.value]
        if compatibility_id is not None:
            sql += (
                " AND (compatibility_id = ? OR "
                "json_extract(artifact_json, '$.compatibility_id') = ?)"
            )
            values.extend([compatibility_id, compatibility_id])
        sql += " ORDER BY cutoff_at, observation_id"
        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        return tuple(_load_observation_row(row) for row in rows)

    def add_track_snapshot(self, artifact: LearningTrackSnapshot) -> bool:
        validate_artifact_integrity(artifact, id_field="snapshot_id")
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_track_snapshots",
                id_column="snapshot_id",
                artifact_id=artifact.snapshot_id,
                digest=artifact.artifact_digest,
                insert_sql="""
                    INSERT INTO learning_track_snapshots VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """,
                values=(
                    artifact.snapshot_id,
                    artifact.artifact_digest,
                    artifact.schema_version,
                    artifact.observation_id,
                    artifact.sampled_at.isoformat(),
                    artifact.source,
                    canonical_json(artifact.snapshot_payload),
                    artifact.captured_at.isoformat(),
                    _artifact_json(artifact),
                ),
            )

    def list_track_snapshots(self, observation_id: str) -> Sequence[LearningTrackSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT artifact_json FROM learning_track_snapshots
                WHERE observation_id = ? ORDER BY sampled_at, source
                """,
                (observation_id,),
            ).fetchall()
        return tuple(_load_json(row, _track_from_dict) for row in rows)

    def add_label(self, artifact: LearningOutcomeLabel) -> bool:
        validate_artifact_integrity(artifact, id_field="label_id")
        values = (
            artifact.label_id,
            artifact.artifact_digest,
            artifact.schema_version,
            artifact.contract_id.value,
            artifact.observation_id,
            artifact.outcome_basis.value,
            artifact.availability.value,
            artifact.outcome,
            canonical_json(artifact.metrics),
            artifact.fingerprint,
            artifact.labeled_at.isoformat(),
            _artifact_json(artifact),
        )
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_outcome_labels",
                id_column="label_id",
                artifact_id=artifact.label_id,
                digest=artifact.artifact_digest,
                insert_sql="""
                    INSERT INTO learning_outcome_labels VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """,
                values=values,
                column_names=_LABEL_COLUMNS,
            )

    def list_labels(self, observation_ids: Sequence[str]) -> Sequence[LearningOutcomeLabel]:
        return _list_labels_with_identity_discovery(self._connect, observation_ids)

    def add_evaluation(self, artifact: LearningEvaluation) -> bool:
        validate_artifact_integrity(artifact, id_field="evaluation_id")
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_evaluations",
                id_column="evaluation_id",
                artifact_id=artifact.evaluation_id,
                digest=artifact.artifact_digest,
                insert_sql="""
                    INSERT INTO learning_evaluations VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """,
                values=(
                    artifact.evaluation_id,
                    artifact.artifact_digest,
                    artifact.schema_version,
                    artifact.contract_id.value,
                    artifact.purpose.value,
                    artifact.method.value,
                    artifact.compatibility_id,
                    artifact.dataset_fingerprint,
                    artifact.split_contract,
                    canonical_json(artifact.population),
                    canonical_json(artifact.exclusions),
                    canonical_json(artifact.metrics),
                    artifact.outcome_basis.value,
                    artifact.readiness.value,
                    artifact.evaluated_at.isoformat(),
                    _artifact_json(artifact),
                ),
            )

    def get_evaluation(self, evaluation_id: str) -> LearningEvaluation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT artifact_json FROM learning_evaluations WHERE evaluation_id = ?",
                (evaluation_id,),
            ).fetchone()
        return None if row is None else _load_json(row, _evaluation_from_dict)

    def list_evaluations(self, purpose: AssessmentPurpose) -> Sequence[LearningEvaluation]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT artifact_json FROM learning_evaluations
                WHERE purpose = ? ORDER BY evaluated_at, evaluation_id
                """,
                (purpose.value,),
            ).fetchall()
        return tuple(_load_json(row, _evaluation_from_dict) for row in rows)

    def add_proposal(self, artifact: LearningPolicyProposal) -> bool:
        validate_artifact_integrity(artifact, id_field="proposal_id")
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_policy_proposals",
                id_column="proposal_id",
                artifact_id=artifact.proposal_id,
                digest=artifact.artifact_digest,
                insert_sql=(
                    "INSERT INTO learning_policy_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                values=(
                    artifact.proposal_id,
                    artifact.artifact_digest,
                    artifact.schema_version,
                    artifact.contract_id.value,
                    artifact.source_evaluation_id,
                    artifact.current_config_hash,
                    canonical_json(artifact.changes),
                    canonical_json(artifact.rationale),
                    artifact.created_at.isoformat(),
                    _artifact_json(artifact),
                ),
            )

    def get_proposal(self, proposal_id: str) -> LearningPolicyProposal | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT artifact_json FROM learning_policy_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return None if row is None else _load_json(row, _proposal_from_dict)

    def list_proposals(self) -> Sequence[LearningPolicyProposal]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT artifact_json FROM learning_policy_proposals
                ORDER BY created_at, proposal_id
                """).fetchall()
        return tuple(_load_json(row, _proposal_from_dict) for row in rows)

    def add_validation(self, artifact: LearningPolicyValidation) -> bool:
        validate_artifact_integrity(artifact, id_field="validation_id")
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_policy_validations",
                id_column="validation_id",
                artifact_id=artifact.validation_id,
                digest=artifact.artifact_digest,
                insert_sql=(
                    "INSERT INTO learning_policy_validations "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                values=(
                    artifact.validation_id,
                    artifact.artifact_digest,
                    artifact.schema_version,
                    artifact.contract_id.value,
                    artifact.proposal_id,
                    artifact.baseline_evaluation_id,
                    artifact.proposed_evaluation_id,
                    artifact.population_fingerprint,
                    canonical_json(artifact.paired_deltas),
                    canonical_json({"issues": artifact.issues}),
                    artifact.status.value,
                    artifact.validated_at.isoformat(),
                    _artifact_json(artifact),
                ),
            )

    def get_validation_for_proposal(self, proposal_id: str) -> LearningPolicyValidation | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_json FROM learning_policy_validations
                WHERE proposal_id = ?
                """,
                (proposal_id,),
            ).fetchone()
        return None if row is None else _load_json(row, _validation_from_dict)

    def list_validations(self) -> Sequence[LearningPolicyValidation]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT artifact_json FROM learning_policy_validations
                ORDER BY validated_at, validation_id
                """).fetchall()
        return tuple(_load_json(row, _validation_from_dict) for row in rows)

    def add_application(self, artifact: LearningPolicyApplication) -> bool:
        validate_artifact_integrity(artifact, id_field="application_id")
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_policy_applications",
                id_column="application_id",
                artifact_id=artifact.application_id,
                digest=artifact.artifact_digest,
                insert_sql=(
                    "INSERT INTO learning_policy_applications "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                values=(
                    artifact.application_id,
                    artifact.artifact_digest,
                    artifact.schema_version,
                    artifact.contract_id.value,
                    artifact.proposal_id,
                    artifact.validation_id,
                    artifact.previous_config_hash,
                    artifact.applied_config_hash,
                    canonical_json(artifact.exact_changes),
                    artifact.confirmation_identity,
                    artifact.applied_at.isoformat(),
                    1,
                    _artifact_json(artifact),
                ),
            )

    def get_application_for_proposal(self, proposal_id: str) -> LearningPolicyApplication | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_json FROM learning_policy_applications
                WHERE proposal_id = ?
                """,
                (proposal_id,),
            ).fetchone()
        return None if row is None else _load_json(row, _application_from_dict)

    def list_applications(self) -> Sequence[LearningPolicyApplication]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT artifact_json FROM learning_policy_applications
                ORDER BY applied_at, application_id
                """).fetchall()
        return tuple(_load_json(row, _application_from_dict) for row in rows)

    @staticmethod
    def _policy_snapshot_insert_values(artifact: ProductionPolicySnapshot) -> tuple[Any, ...]:
        return (
            artifact.snapshot_id,
            artifact.schema_version,
            artifact.contract_id.value,
            artifact.purpose.value,
            artifact.learning_observation_contract_id,
            artifact.producer_observation_contract,
            artifact.compatibility_id,
            artifact.policy_id,
            artifact.policy_version,
            artifact.decision_type,
            artifact.semantic_engine_contract_id,
            artifact.material_config_hash,
            canonical_json(artifact.canonical_payload),
            artifact.payload_digest,
            artifact.source_revision,
            artifact.created_at.isoformat(),
            _artifact_json(artifact),
        )

    _POLICY_SNAPSHOT_INSERT_SQL = """
        INSERT INTO learning_policy_snapshots VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """

    def add_policy_snapshot(self, artifact: ProductionPolicySnapshot) -> bool:
        validate_policy_snapshot_integrity(artifact)
        with self._connect() as connection:
            return _immutable_insert(
                connection,
                table="learning_policy_snapshots",
                id_column="snapshot_id",
                artifact_id=artifact.snapshot_id,
                digest=artifact.payload_digest,
                digest_column="payload_digest",
                insert_sql=self._POLICY_SNAPSHOT_INSERT_SQL,
                values=self._policy_snapshot_insert_values(artifact),
                column_names=_POLICY_SNAPSHOT_COLUMNS,
            )

    def add_policy_snapshots_atomic(
        self, artifacts: Sequence[ProductionPolicySnapshot]
    ) -> tuple[int, int]:
        """Write a closed snapshot set in one BEGIN IMMEDIATE transaction.

        Preflight validates every artifact, then inserts/reuses under one
        connection so a mid-set digest conflict leaves zero new rows.
        """
        if not artifacts:
            raise LearningContractError("policy snapshot batch must be non-empty")
        seen_ids: set[str] = set()
        for artifact in artifacts:
            validate_policy_snapshot_integrity(artifact)
            if artifact.snapshot_id in seen_ids:
                raise LearningContractError(
                    f"duplicate snapshot_id in batch: {artifact.snapshot_id}"
                )
            seen_ids.add(artifact.snapshot_id)

        inserted = 0
        reused = 0
        # Explicit connection lifecycle so one BEGIN IMMEDIATE covers the
        # whole batch (``with connection`` would auto-commit per-block).
        connection = connect_learning_database(self._db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            for artifact in artifacts:
                wrote = _immutable_insert(
                    connection,
                    table="learning_policy_snapshots",
                    id_column="snapshot_id",
                    artifact_id=artifact.snapshot_id,
                    digest=artifact.payload_digest,
                    digest_column="payload_digest",
                    insert_sql=self._POLICY_SNAPSHOT_INSERT_SQL,
                    values=self._policy_snapshot_insert_values(artifact),
                    column_names=_POLICY_SNAPSHOT_COLUMNS,
                )
                if wrote:
                    inserted += 1
                else:
                    reused += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return inserted, reused

    def get_policy_snapshot(self, snapshot_id: str) -> ProductionPolicySnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_POLICY_SELECT} FROM learning_policy_snapshots "
                "WHERE snapshot_id = ? OR json_extract(artifact_json, '$.snapshot_id') = ?",
                (snapshot_id, snapshot_id),
            ).fetchone()
        return None if row is None else _load_policy_row(row)

    def get_policy_snapshot_by_binding(
        self,
        *,
        purpose: AssessmentPurpose,
        compatibility_id: str,
        policy_id: str,
    ) -> ProductionPolicySnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT {_POLICY_SELECT} FROM learning_policy_snapshots
                WHERE (
                    (purpose = ? AND compatibility_id = ? AND policy_id = ?)
                    OR (
                        json_extract(artifact_json, '$.purpose') = ?
                        AND json_extract(artifact_json, '$.compatibility_id') = ?
                        AND json_extract(artifact_json, '$.policy_id') = ?
                    )
                )
                """,
                (
                    purpose.value,
                    compatibility_id,
                    policy_id,
                    purpose.value,
                    compatibility_id,
                    policy_id,
                ),
            ).fetchone()
        return None if row is None else _load_policy_row(row)

    def list_policy_snapshots(
        self,
        *,
        purpose: AssessmentPurpose,
        compatibility_id: str,
    ) -> Sequence[ProductionPolicySnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {_POLICY_SELECT} FROM learning_policy_snapshots
                WHERE (purpose = ? AND compatibility_id = ?)
                   OR (
                        json_extract(artifact_json, '$.purpose') = ?
                        AND json_extract(artifact_json, '$.compatibility_id') = ?
                   )
                ORDER BY policy_id
                """,
                (purpose.value, compatibility_id, purpose.value, compatibility_id),
            ).fetchall()
        return tuple(_load_policy_row(row) for row in rows)


def connect_learning_database_readonly(db_path: Path) -> sqlite3.Connection:
    """Open an existing learning DB read-only. Never creates files or schema."""

    path = Path(db_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"learning database does not exist: {path}")
    # URI mode=ro fails closed if the file is missing and never creates it.
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def expected_label_ids_for_observations(observation_ids: Sequence[str]) -> tuple[str, ...]:
    """Deterministic label_id candidates for each observation × label contract."""
    out: list[str] = []
    for observation_id in observation_ids:
        for contract in _LABEL_DISCOVERY_CONTRACTS:
            out.append(
                stable_learning_id(
                    contract,
                    {"observation_id": observation_id, "contract_id": contract},
                )
            )
    return tuple(out)


def _list_labels_with_identity_discovery(
    connect: Callable[[], sqlite3.Connection],
    observation_ids: Sequence[str],
) -> Sequence[LearningOutcomeLabel]:
    """Discover labels by parent observation_id OR expected label_id identity.

    Dual observation_id (column / JSON) alone is insufficient: a coherent relink
    that rewrites both representations can hide a row. Expected label_id is
    derived solely from the requested parent observation_id + contract and still
    finds the original row when the stored linkage was corrupted.
    """
    if not observation_ids:
        return ()
    obs_ids = tuple(observation_ids)
    label_ids = expected_label_ids_for_observations(obs_ids)
    obs_ph = ",".join("?" for _ in obs_ids)
    if label_ids:
        label_ph = ",".join("?" for _ in label_ids)
        sql = f"""
            SELECT {_LABEL_SELECT} FROM learning_outcome_labels
            WHERE observation_id IN ({obs_ph})
               OR json_extract(artifact_json, '$.observation_id') IN ({obs_ph})
               OR label_id IN ({label_ph})
            ORDER BY observation_id, contract_id
            """  # noqa: S608
        params: tuple[Any, ...] = obs_ids + obs_ids + label_ids
    else:
        sql = f"""
            SELECT {_LABEL_SELECT} FROM learning_outcome_labels
            WHERE observation_id IN ({obs_ph})
               OR json_extract(artifact_json, '$.observation_id') IN ({obs_ph})
            ORDER BY observation_id, contract_id
            """  # noqa: S608
        params = obs_ids + obs_ids
    with connect() as connection:
        rows = connection.execute(sql, params).fetchall()
    return tuple(_load_label_row(row) for row in rows)


class SQLiteLearningArtifactReadRepository:
    """Read-only learning projections for status / research (no schema ensure).

    Constructor refuses missing DB paths and never calls ensure_learning_schema.
    Write methods are intentionally absent.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        if not self._db_path.is_file():
            raise FileNotFoundError(
                f"learning database does not exist (status is read-only): {self._db_path}"
            )

    def _connect(self) -> sqlite3.Connection:
        return connect_learning_database_readonly(self._db_path)

    def list_observations(
        self, purpose: AssessmentPurpose, *, compatibility_id: str | None = None
    ) -> Sequence[LearningObservation]:
        # Parentheses required: AND binds tighter than OR.
        sql = (
            f"SELECT {_OBS_SELECT} FROM learning_observations "
            "WHERE (purpose = ? OR json_extract(artifact_json, '$.purpose') = ?)"
        )
        values: list[str] = [purpose.value, purpose.value]
        if compatibility_id is not None:
            sql += (
                " AND (compatibility_id = ? OR "
                "json_extract(artifact_json, '$.compatibility_id') = ?)"
            )
            values.extend([compatibility_id, compatibility_id])
        sql += " ORDER BY cutoff_at, observation_id"
        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        return tuple(_load_observation_row(row) for row in rows)

    def list_labels(self, observation_ids: Sequence[str]) -> Sequence[LearningOutcomeLabel]:
        return _list_labels_with_identity_discovery(self._connect, observation_ids)

    def list_policy_snapshots(
        self,
        *,
        purpose: AssessmentPurpose,
        compatibility_id: str,
    ) -> Sequence[ProductionPolicySnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {_POLICY_SELECT} FROM learning_policy_snapshots
                WHERE (purpose = ? AND compatibility_id = ?)
                   OR (
                        json_extract(artifact_json, '$.purpose') = ?
                        AND json_extract(artifact_json, '$.compatibility_id') = ?
                   )
                ORDER BY policy_id
                """,
                (purpose.value, compatibility_id, purpose.value, compatibility_id),
            ).fetchall()
        return tuple(_load_policy_row(row) for row in rows)
