"""CLI regression tests for `saham analyze signal-labels` (HIGH-2 Finding 2).

An incompatible-schema selected observation must fail safely: exit non-zero,
print the canonical-schema error, never index an empty labels tuple, and
never fall through to the summary output.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app

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
            "analyze",
            "signal-labels",
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
        "expected schema 3, found 2. No label was generated."
    ) in result.output
    assert "IndexError" not in result.output
    assert "Traceback" not in result.output
    assert "Signal Forward Labels" not in result.output
    assert "Labels:" not in result.output
