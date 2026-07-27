import sqlite3

import pytest

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.infrastructure.persistence.learning_clean_break import (
    LEARNING_TABLES,
    apply_learning_clean_break,
)


def _seed_legacy_database(path) -> None:
    connection = sqlite3.connect(path)
    for table in (
        "candidate_observations",
        "candidate_observations_quarantine",
        "observation_risk_assessments",
        "signal_forward_labels",
        "signal_forward_labels_quarantine",
    ):
        connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
    connection.execute(
        "CREATE TABLE _schema_migrations "
        "(namespace TEXT, version INTEGER, PRIMARY KEY(namespace, version))"
    )
    for namespace in (
        "candidate_observations",
        "observation_risk_assessments",
        "signal_forward_labels",
        "candles",
    ):
        connection.execute(
            "INSERT INTO _schema_migrations(namespace, version) VALUES (?, 1)",
            (namespace,),
        )
    connection.execute("INSERT INTO candidate_observations_quarantine DEFAULT VALUES")
    connection.execute("INSERT INTO signal_forward_labels_quarantine DEFAULT VALUES")
    connection.commit()
    connection.close()


def test_clean_break_is_atomic_and_starts_canonical_tables_empty(tmp_path) -> None:
    path = tmp_path / "data.db"
    _seed_legacy_database(path)

    report = apply_learning_clean_break(path)

    assert report.before_counts["candidate_observations_quarantine"] == 1
    assert report.before_counts["signal_forward_labels_quarantine"] == 1
    assert report.deleted_migration_records == 3
    connection = sqlite3.connect(path)
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert set(LEARNING_TABLES) <= tables
    assert (
        not {
            "candidate_observations",
            "candidate_observations_quarantine",
            "observation_risk_assessments",
            "signal_forward_labels",
            "signal_forward_labels_quarantine",
        }
        & tables
    )
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM _schema_migrations WHERE namespace = 'candles'"
        ).fetchone()[0]
        == 1
    )
    assert all(
        connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0
        for table in LEARNING_TABLES
    )
    connection.close()


def test_clean_break_rolls_back_when_existing_learning_table_is_nonempty(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "data.db"
    _seed_legacy_database(path)

    def invalid_schema(connection):
        connection.execute("CREATE TABLE learning_observations (observation_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO learning_observations VALUES ('unexpected')")
        for table in LEARNING_TABLES[1:]:
            connection.execute(f'CREATE TABLE "{table}" (id TEXT)')

    monkeypatch.setattr(
        "src.infrastructure.persistence.learning_clean_break.create_learning_schema",
        invalid_schema,
    )

    with pytest.raises(LearningContractError, match="must start empty"):
        apply_learning_clean_break(path)

    connection = sqlite3.connect(path)
    assert (
        connection.execute("SELECT COUNT(*) FROM candidate_observations_quarantine").fetchone()[0]
        == 1
    )
    connection.close()
