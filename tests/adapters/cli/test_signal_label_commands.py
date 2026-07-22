"""CLI regression tests for `saham research signal labels` (HIGH-2 Finding 2).

An incompatible-schema selected observation must fail safely: exit non-zero,
print the canonical-schema error, never index an empty labels tuple, and
never fall through to the summary output.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)

runner = CliRunner()


def _seed_legacy_observation(db_path: Path) -> None:
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )

    SQLiteCandidateObservationsRepository(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json, config_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "BBCA",
            "2026-07-01",
            "2026-07-01T09:00:00",
            2,
            "{}",
            "legacy-hash",
        ),
    )
    conn.commit()
    conn.close()


def test_generate_rejects_incompatible_observation_schema(tmp_path):
    db_path = tmp_path / "signal_labels.db"
    _seed_legacy_observation(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "labels",
            "2026-07-01",
            "--ticker",
            "BBCA",
            "--generate",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1, result.output
    assert (
        "Stored observation for BBCA on 2026-07-01 is not canonical: "
        f"expected schema {CANDIDATE_OBSERVATION_SCHEMA_VERSION}, found 2. No label was generated."
    ) in result.output
    assert "IndexError" not in result.output
    assert "Traceback" not in result.output
    assert "Signal Forward Labels" not in result.output
    assert "Labels:" not in result.output


def _seed_current_schema_empty_hash_observation(db_path: Path) -> None:
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )

    SQLiteCandidateObservationsRepository(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json, config_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "BBCA",
            "2026-07-01",
            "2026-07-01T09:00:00",
            CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            "{}",
            "",
        ),
    )
    conn.commit()
    conn.close()


def test_generate_rejects_current_schema_empty_hash_observation_table_mode(tmp_path):
    db_path = tmp_path / "signal_labels.db"
    _seed_current_schema_empty_hash_observation(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "labels",
            "2026-07-01",
            "--ticker",
            "BBCA",
            "--generate",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1, result.output
    assert (
        "Stored observation for BBCA on 2026-07-01 has no canonical config_hash. "
        "No label was generated."
    ) in result.output
    assert "IndexError" not in result.output
    assert "Traceback" not in result.output
    assert "Signal Forward Labels" not in result.output
    assert "Labels:" not in result.output


def _seed_current_schema_removed_market_context_observation(db_path: Path) -> None:
    import json

    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )

    SQLiteCandidateObservationsRepository(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json, config_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "BBCA",
            "2026-07-01",
            "2026-07-01T09:00:00",
            CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            json.dumps(
                {
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                    "sub_signal_fingerprint": {
                        "alpha_trigger_route_metadata": [
                            {"group": "market_context", "score": 75.0},
                        ],
                    },
                }
            ),
            "valid-hash",
        ),
    )
    conn.commit()
    conn.close()


def test_generate_rejects_observation_violating_current_contract(tmp_path):
    """SECTOR-CONTEXT-IDENTITY: a stored schema-4 observation carrying the
    removed market_context group must fail closed with the current-contract
    error and a non-zero exit, generating no label."""
    db_path = tmp_path / "signal_labels.db"
    _seed_current_schema_removed_market_context_observation(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "labels",
            "2026-07-01",
            "--ticker",
            "BBCA",
            "--generate",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1, result.output
    assert (
        "Stored observation for BBCA on 2026-07-01 violates the current "
        "signal observation contract. No label was generated."
    ) in result.output
    assert "IndexError" not in result.output
    assert "Traceback" not in result.output
    assert "Signal Forward Labels" not in result.output
    assert "Labels:" not in result.output


def test_generate_rejects_current_schema_empty_hash_observation_json_mode(tmp_path):
    db_path = tmp_path / "signal_labels.db"
    _seed_current_schema_empty_hash_observation(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "labels",
            "2026-07-01",
            "--ticker",
            "BBCA",
            "--generate",
            "--format",
            "json",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1, result.output
    assert (
        "Stored observation for BBCA on 2026-07-01 has no canonical config_hash. "
        "No label was generated."
    ) in result.output
    assert "IndexError" not in result.output
    assert "Traceback" not in result.output
    assert "Signal Forward Labels" not in result.output
    assert "Labels:" not in result.output


def _count_rows(db_path: Path, table: str) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_summary_without_generate_is_read_only(tmp_path):
    """DQ-011 D11-4: summary path must not write labels or observations."""
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )

    db_path = tmp_path / "signal_labels.db"
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)
    before_obs = _count_rows(db_path, "candidate_observations")
    before_labels = _count_rows(db_path, "signal_forward_labels")

    result = runner.invoke(
        app,
        ["research", "signal", "labels", "2026-07-01", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Signal Forward Labels" in result.output
    assert _count_rows(db_path, "candidate_observations") == before_obs
    assert _count_rows(db_path, "signal_forward_labels") == before_labels


def test_generate_rejection_does_not_write_labels(tmp_path):
    """DQ-011 D11-4: incompatible generate path writes nothing."""
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )

    db_path = tmp_path / "signal_labels.db"
    _seed_legacy_observation(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)
    before_labels = _count_rows(db_path, "signal_forward_labels")

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "labels",
            "2026-07-01",
            "--ticker",
            "BBCA",
            "--generate",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1, result.output
    assert _count_rows(db_path, "signal_forward_labels") == before_labels
    assert _count_rows(db_path, "candidate_observations") == 1
