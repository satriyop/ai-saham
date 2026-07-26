"""SQLite implementation of the database-owned learning artifact ports."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar

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
    ValidationStatus,
    canonical_json,
    validate_artifact_integrity,
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
)

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


def create_learning_schema(connection: sqlite3.Connection) -> None:
    """Create only the seven canonical tables and their indexes."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            namespace TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (namespace, version)
        )
        """
    )
    for statement in LEARNING_SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        """
        INSERT OR IGNORE INTO _schema_migrations(namespace, version)
        VALUES (?, 1)
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


def _immutable_insert(
    connection: sqlite3.Connection,
    *,
    table: str,
    id_column: str,
    artifact_id: str,
    digest: str,
    insert_sql: str,
    values: tuple[Any, ...],
) -> bool:
    existing = connection.execute(
        f"SELECT artifact_digest FROM {table} WHERE {id_column} = ?",  # noqa: S608
        (artifact_id,),
    ).fetchone()
    if existing is not None:
        if existing["artifact_digest"] == digest:
            return False
        raise LearningContractError(
            f"immutable artifact conflict for {table}.{artifact_id}"
        )
    connection.execute(insert_sql, values)
    return True


def _load_json(row: sqlite3.Row, loader: Callable[[dict[str, Any]], Artifact]) -> Artifact:
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


class SQLiteLearningArtifactRepository:
    """One transaction-safe implementation shared by the seven narrow ports."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        ensure_learning_schema(self._db_path)

    def _connect(self) -> sqlite3.Connection:
        return connect_learning_database(self._db_path)

    def add_observation(self, artifact: LearningObservation) -> bool:
        validate_artifact_integrity(artifact, id_field="observation_id")
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
                values=(
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
                ),
            )

    def get_observation(self, observation_id: str) -> LearningObservation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT artifact_json FROM learning_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
        return None if row is None else _load_json(row, _observation_from_dict)

    def list_observations(
        self, purpose: AssessmentPurpose, *, compatibility_id: str | None = None
    ) -> Sequence[LearningObservation]:
        sql = "SELECT artifact_json FROM learning_observations WHERE purpose = ?"
        values: list[str] = [purpose.value]
        if compatibility_id is not None:
            sql += " AND compatibility_id = ?"
            values.append(compatibility_id)
        sql += " ORDER BY cutoff_at, observation_id"
        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        return tuple(_load_json(row, _observation_from_dict) for row in rows)

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
                values=(
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
                ),
            )

    def list_labels(self, observation_ids: Sequence[str]) -> Sequence[LearningOutcomeLabel]:
        if not observation_ids:
            return ()
        placeholders = ",".join("?" for _ in observation_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT artifact_json FROM learning_outcome_labels
                WHERE observation_id IN ({placeholders})
                ORDER BY observation_id, contract_id
                """,  # noqa: S608
                tuple(observation_ids),
            ).fetchall()
        return tuple(_load_json(row, _label_from_dict) for row in rows)

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

    def list_evaluations(
        self, purpose: AssessmentPurpose
    ) -> Sequence[LearningEvaluation]:
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
                    "INSERT INTO learning_policy_proposals "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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

    def get_validation_for_proposal(
        self, proposal_id: str
    ) -> LearningPolicyValidation | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_json FROM learning_policy_validations
                WHERE proposal_id = ?
                """,
                (proposal_id,),
            ).fetchone()
        return None if row is None else _load_json(row, _validation_from_dict)

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

    def get_application_for_proposal(
        self, proposal_id: str
    ) -> LearningPolicyApplication | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_json FROM learning_policy_applications
                WHERE proposal_id = ?
                """,
                (proposal_id,),
            ).fetchone()
        return None if row is None else _load_json(row, _application_from_dict)
