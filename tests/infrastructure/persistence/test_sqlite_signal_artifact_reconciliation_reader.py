"""Tests for SQLiteSignalArtifactReconciliationReader (DQ-001E)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.infrastructure.persistence.sqlite_signal_artifact_reconciliation_reader import (
    SQLiteSignalArtifactReconciliationReader,
)


def _create_candidate_observations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE candidate_observations (id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, "
        "snapshot_date TEXT NOT NULL, captured_at TEXT NOT NULL, schema_version INTEGER "
        "NOT NULL, payload_json TEXT NOT NULL, workflow TEXT NOT NULL, "
        "window_sessions INTEGER NOT NULL, data_as_of_date TEXT NOT NULL, "
        "config_hash TEXT NOT NULL DEFAULT '')"
    )


def _create_signal_forward_labels(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE signal_forward_labels (id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, "
        "signal_date TEXT NOT NULL, horizon TEXT NOT NULL, "
        "observation_captured_at TEXT NOT NULL DEFAULT '', outcome_label TEXT NOT NULL, "
        "fingerprint_json TEXT NOT NULL, schema_version INTEGER NOT NULL)"
    )


def _create_market_context_snapshots(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE market_context_snapshots (as_of_date TEXT NOT NULL PRIMARY KEY, "
        "regime TEXT NOT NULL, conviction REAL NOT NULL, signal_multiplier REAL NOT NULL, "
        "gate_tightening INTEGER NOT NULL, factors_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )


def _create_regime_observations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE regime_observations (observation_date TEXT NOT NULL PRIMARY KEY, "
        "schema_version INTEGER NOT NULL DEFAULT 1, regime TEXT NOT NULL, "
        "regime_score REAL NOT NULL, regime_confidence REAL NOT NULL, "
        "regime_stability TEXT NOT NULL, detection_inputs_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )


@pytest.fixture
def full_schema_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "artifact_reconcile.db"
    conn = sqlite3.connect(str(db_path))
    _create_candidate_observations(conn)
    _create_signal_forward_labels(conn)
    _create_market_context_snapshots(conn)
    _create_regime_observations(conn)
    conn.commit()
    conn.close()
    return db_path


# ── candidate_observations_identity ──────────────────────────────────────


def test_missing_database_reports_not_exists():
    reader = SQLiteSignalArtifactReconciliationReader(Path("/nonexistent/does_not_exist.db"))

    assert reader.observe_candidate_observations_identity().exists is False


def test_missing_table_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)

    assert reader.observe_candidate_observations_identity().exists is False
    assert reader.observe_signal_forward_labels_linkage().exists is False
    assert reader.observe_market_context_snapshot_identity().exists is False
    assert reader.observe_regime_observations_identity().exists is False


def test_candidate_observation_canonical_row_empty_identity_fails(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
        "window_sessions, data_as_of_date, config_hash) "
        f"VALUES ('', '2026-01-02', '2026-01-02T00:00:00', "
        f"{CANDIDATE_OBSERVATION_SCHEMA_VERSION}, '{{}}', 'w', 5, "
        "'2026-01-02', 'abc123')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_candidate_observations_identity()

    assert raw.canonical_row_count == 1
    assert raw.canonical_missing_identity_count == 1


def test_candidate_observation_canonical_row_invalid_window_sessions_fails(
    full_schema_db: Path,
):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
        "window_sessions, data_as_of_date, config_hash) "
        f"VALUES ('BBCA', '2026-01-02', '2026-01-02T00:00:00', "
        f"{CANDIDATE_OBSERVATION_SCHEMA_VERSION}, '{{}}', 'w', 0, "
        "'2026-01-02', 'abc123')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_candidate_observations_identity()

    assert raw.canonical_missing_identity_count == 1


def test_candidate_observation_legacy_empty_config_hash_warns(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
        "window_sessions, data_as_of_date, config_hash) "
        "VALUES ('BBCA', '2026-01-02', '2026-01-02T00:00:00', 1, '{}', '', 0, '', '')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_candidate_observations_identity()

    assert raw.legacy_row_count == 1
    assert raw.canonical_row_count == 0
    # Legacy rows are excluded from the canonical-identity check entirely.
    assert raw.canonical_missing_identity_count == 0


def test_duplicate_canonical_candidate_identity_warns(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    for _ in range(2):
        conn.execute(
            "INSERT INTO candidate_observations "
            "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
            "window_sessions, data_as_of_date, config_hash) "
            f"VALUES ('BBCA', '2026-01-02', '2026-01-02T00:00:00', "
            f"{CANDIDATE_OBSERVATION_SCHEMA_VERSION}, '{{}}', 'w', 5, "
            "'2026-01-02', 'abc123')"
        )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_candidate_observations_identity()

    assert raw.duplicate_canonical_identity_count == 1


def test_invalid_candidate_payload_json_fails(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
        "window_sessions, data_as_of_date, config_hash) "
        "VALUES ('BBCA', '2026-01-02', '2026-01-02T00:00:00', 1, 'not-json', 'w', 5, "
        "'2026-01-02', '')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_candidate_observations_identity()

    assert raw.invalid_payload_json_count == 1


def test_candidate_payload_missing_schema_marker_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
        "window_sessions, data_as_of_date, config_hash) "
        "VALUES ('BBCA', '2026-01-02', '2026-01-02T00:00:00', 1, '{\"foo\": 1}', 'w', 5, "
        "'2026-01-02', '')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_candidate_observations_identity()

    assert raw.payload_missing_schema_marker_count == 1


def test_partial_candidate_observations_schema_returns_schema_insufficient(tmp_path: Path):
    db_path = tmp_path / "partial_candidate.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE candidate_observations (ticker TEXT)")
    conn.execute("INSERT INTO candidate_observations VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)
    raw = reader.observe_candidate_observations_identity()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "snapshot_date" in raw.missing_columns
    assert raw.row_count == 1


# ── signal_forward_labels_identity_linkage ───────────────────────────────


def test_signal_label_invalid_fingerprint_json_fails(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, outcome_label, "
        "fingerprint_json, schema_version) "
        "VALUES ('BBCA', '2026-01-02', '5d', '2026-01-02T00:00:00', 'SUCCESS', "
        "'not-json', 1)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_signal_forward_labels_linkage()

    assert raw.invalid_fingerprint_json_count == 1


def test_signal_label_linkage_reported_honestly_when_schema_lacks_identity(tmp_path: Path):
    # candidate_observations does not exist at all -> linkage cannot be proven.
    db_path = tmp_path / "labels_only.db"
    conn = sqlite3.connect(str(db_path))
    _create_signal_forward_labels(conn)
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, outcome_label, "
        "fingerprint_json, schema_version) "
        "VALUES ('BBCA', '2026-01-02', '5d', '2026-01-02T00:00:00', 'SUCCESS', '{}', 1)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)
    raw = reader.observe_signal_forward_labels_linkage()

    assert raw.linkage_provable is False
    assert raw.orphan_linkage_count == 0


def test_signal_label_orphan_linkage_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, outcome_label, "
        "fingerprint_json, schema_version) "
        "VALUES ('BBCA', '2026-01-02', '5d', '2026-01-02T00:00:00', 'SUCCESS', '{}', 1)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_signal_forward_labels_linkage()

    assert raw.linkage_provable is True
    assert raw.orphan_linkage_count == 1


def test_signal_label_linkage_matches_candidate_observation(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
        "window_sessions, data_as_of_date, config_hash) "
        "VALUES ('BBCA', '2026-01-02', '2026-01-02T00:00:00', 1, '{}', 'w', 5, "
        "'2026-01-02', '')"
    )
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, outcome_label, "
        "fingerprint_json, schema_version) "
        "VALUES ('BBCA', '2026-01-02', '5d', '2026-01-02T00:00:00', 'SUCCESS', '{}', 1)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_signal_forward_labels_linkage()

    assert raw.linkage_provable is True
    assert raw.orphan_linkage_count == 0


def test_partial_signal_forward_labels_schema_returns_schema_insufficient(tmp_path: Path):
    db_path = tmp_path / "partial_labels.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE signal_forward_labels (ticker TEXT)")
    conn.execute("INSERT INTO signal_forward_labels VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)
    raw = reader.observe_signal_forward_labels_linkage()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "signal_date" in raw.missing_columns


# ── market_context_snapshot_identity ─────────────────────────────────────


def test_market_context_null_regime_fails(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO market_context_snapshots "
        "(as_of_date, regime, conviction, signal_multiplier, gate_tightening, "
        "factors_json, created_at) "
        "VALUES ('2026-01-02', 'unknown', 0.5, 1.0, 0, '[]', '2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_market_context_snapshot_identity()

    assert raw.invalid_regime_count == 1


def test_market_context_invalid_non_unknown_regime_value_fails(full_schema_db: Path):
    # Regression: the domain MarketRegime enum is RISK_ON/NEUTRAL/RISK_OFF/
    # VOLATILE. A value like "BULLISH" is neither null, empty, nor the
    # literal "unknown" sentinel, but is still not a valid regime and must
    # be caught, not silently accepted.
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO market_context_snapshots "
        "(as_of_date, regime, conviction, signal_multiplier, gate_tightening, "
        "factors_json, created_at) "
        "VALUES ('2026-01-02', 'BULLISH', 0.5, 1.0, 0, '[]', '2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_market_context_snapshot_identity()

    assert raw.invalid_regime_count == 1


def test_market_context_volatile_regime_is_valid(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO market_context_snapshots "
        "(as_of_date, regime, conviction, signal_multiplier, gate_tightening, "
        "factors_json, created_at) "
        "VALUES ('2026-01-02', 'VOLATILE', 0.5, 1.0, 0, '[]', '2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_market_context_snapshot_identity()

    assert raw.invalid_regime_count == 0


def test_market_context_invalid_factors_json_fails(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO market_context_snapshots "
        "(as_of_date, regime, conviction, signal_multiplier, gate_tightening, "
        "factors_json, created_at) "
        "VALUES ('2026-01-02', 'NEUTRAL', 0.5, 1.0, 0, 'not-json', '2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_market_context_snapshot_identity()

    assert raw.invalid_factors_json_count == 1


def test_market_context_partial_schema_returns_schema_insufficient_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_market_context.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE market_context_snapshots (as_of_date TEXT)")
    conn.execute("INSERT INTO market_context_snapshots VALUES ('2026-01-02')")
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)
    raw = reader.observe_market_context_snapshot_identity()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "regime" in raw.missing_columns
    assert raw.row_count == 1


def test_missing_market_context_table_warns_not_crash(tmp_path: Path):
    db_path = tmp_path / "no_market_context.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)
    raw = reader.observe_market_context_snapshot_identity()

    assert raw.exists is False


# ── regime_observations_identity ─────────────────────────────────────────


def test_regime_observation_null_regime_fails(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO regime_observations "
        "(observation_date, regime, regime_score, regime_confidence, regime_stability, "
        "detection_inputs_json, created_at, updated_at) "
        "VALUES ('2026-01-02', '', 0.5, 0.5, 'STABLE', '{}', '2026-01-02T00:00:00', "
        "'2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_regime_observations_identity()

    assert raw.invalid_regime_count == 1


def test_regime_observation_unknown_regime_fails(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO regime_observations "
        "(observation_date, regime, regime_score, regime_confidence, regime_stability, "
        "detection_inputs_json, created_at, updated_at) "
        "VALUES ('2026-01-02', 'UNKNOWN', 0.5, 0.5, 'STABLE', '{}', '2026-01-02T00:00:00', "
        "'2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_regime_observations_identity()

    assert raw.invalid_regime_count == 1


def test_regime_observation_invalid_non_unknown_regime_value_fails(full_schema_db: Path):
    # Regression: same MarketRegime enum gap as market_context_snapshots —
    # "BEARISH" is neither null, empty, nor "unknown" but is still invalid.
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO regime_observations "
        "(observation_date, regime, regime_score, regime_confidence, regime_stability, "
        "detection_inputs_json, created_at, updated_at) "
        "VALUES ('2026-01-02', 'BEARISH', 0.5, 0.5, 'STABLE', '{}', '2026-01-02T00:00:00', "
        "'2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_regime_observations_identity()

    assert raw.invalid_regime_count == 1


def test_regime_observation_volatile_regime_is_valid(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO regime_observations "
        "(observation_date, regime, regime_score, regime_confidence, regime_stability, "
        "detection_inputs_json, created_at, updated_at) "
        "VALUES ('2026-01-02', 'VOLATILE', 0.5, 0.5, 'STABLE', '{}', '2026-01-02T00:00:00', "
        "'2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    raw = reader.observe_regime_observations_identity()

    assert raw.invalid_regime_count == 0


def test_missing_regime_observations_table_warns_not_crash(tmp_path: Path):
    db_path = tmp_path / "no_regime.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)
    raw = reader.observe_regime_observations_identity()

    assert raw.exists is False


def test_regime_observations_partial_schema_returns_schema_insufficient(tmp_path: Path):
    db_path = tmp_path / "partial_regime.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE regime_observations (observation_date TEXT)")
    conn.execute("INSERT INTO regime_observations VALUES ('2026-01-02')")
    conn.commit()
    conn.close()

    reader = SQLiteSignalArtifactReconciliationReader(db_path)
    raw = reader.observe_regime_observations_identity()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "regime" in raw.missing_columns


# ── learning_observations_risk_pit ───────────────────────────────────────


def _create_learning_observations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE learning_observations (
            observation_id TEXT PRIMARY KEY,
            purpose TEXT NOT NULL,
            decision_payload_json TEXT NOT NULL
        )
        """
    )


def _payload(
    *,
    ticker: str = "BBCA",
    session: str = "2026-06-02",
    risk_snap: str | None = "2026-06-02",
    gate_snap: str | None = "2026-06-02",
    canonical_window: int | None = 7,
    include_risk: bool = True,
    features_window_key: str | None = None,
) -> str:
    import json

    window_key = features_window_key
    if window_key is None:
        window_key = str(canonical_window) if canonical_window is not None else "7"
    pack: dict = {}
    if include_risk:
        risk: dict = {}
        if risk_snap is not None:
            risk["snapshot_date"] = risk_snap
        if gate_snap is not None:
            risk["gate_context"] = {"snapshot_date": gate_snap}
        pack["risk"] = risk
    body: dict = {
        "ticker": ticker,
        "session_date": session,
        "features_by_window": {window_key: pack},
    }
    if canonical_window is not None:
        body["canonical_window"] = canonical_window
    return json.dumps(body)


def test_learning_risk_pit_clean_rows(tmp_path: Path):
    db = tmp_path / "clean.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        ("o1", "ACCUMULATION_DISCOVERY", _payload()),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.exists is True
    assert raw.row_count == 1
    assert raw.risk_snapshot_after_session_count == 0
    assert raw.gate_context_session_mismatch_count == 0
    assert raw.risk_snapshot_unreadable_count == 0


def test_learning_risk_pit_contaminated_shape(tmp_path: Path):
    db = tmp_path / "bad.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        (
            "o1",
            "ACCUMULATION_DISCOVERY",
            _payload(
                ticker="GOTO",
                session="2026-06-02",
                risk_snap="2026-07-28",
                gate_snap="2026-06-02",
            ),
        ),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.risk_snapshot_after_session_count == 1
    assert raw.risk_snapshot_after_session_samples[0]["ticker"] == "GOTO"
    assert raw.risk_snapshot_after_session_samples[0]["session_date"] == "2026-06-02"
    assert raw.risk_snapshot_after_session_samples[0]["risk_snapshot_date"] == "2026-07-28"
    assert raw.gate_context_session_mismatch_count == 0


def test_learning_risk_pit_sample_capped_at_10(tmp_path: Path):
    db = tmp_path / "many.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    for i in range(15):
        conn.execute(
            "INSERT INTO learning_observations VALUES (?, ?, ?)",
            (
                f"o{i}",
                "ACCUMULATION_DISCOVERY",
                _payload(
                    ticker=f"T{i}",
                    session="2026-06-02",
                    risk_snap="2026-07-28",
                ),
            ),
        )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.risk_snapshot_after_session_count == 15
    assert len(raw.risk_snapshot_after_session_samples) == 10


def test_learning_risk_pit_no_risk_block_not_defect(tmp_path: Path):
    db = tmp_path / "norisk.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        ("o1", "ACCUMULATION_DISCOVERY", _payload(include_risk=False)),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.row_count == 1
    assert raw.risk_snapshot_after_session_count == 0
    assert raw.risk_snapshot_unreadable_count == 0


def test_learning_risk_pit_invalid_json_unreadable(tmp_path: Path):
    db = tmp_path / "badjson.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        ("o1", "ACCUMULATION_DISCOVERY", "{not-json"),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.risk_snapshot_unreadable_count == 1
    assert raw.risk_snapshot_after_session_count == 0


def test_learning_risk_pit_missing_canonical_window_falls_back_to_7(tmp_path: Path):
    db = tmp_path / "fallback.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        (
            "o1",
            "ACCUMULATION_DISCOVERY",
            _payload(
                canonical_window=None,
                features_window_key="7",
                session="2026-06-02",
                risk_snap="2026-07-28",
            ),
        ),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.risk_snapshot_after_session_count == 1


def test_learning_risk_pit_earlier_risk_not_flagged(tmp_path: Path):
    db = tmp_path / "earlier.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        (
            "o1",
            "ACCUMULATION_DISCOVERY",
            _payload(session="2026-06-10", risk_snap="2026-06-09", gate_snap="2026-06-10"),
        ),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.risk_snapshot_after_session_count == 0


def test_learning_risk_pit_ignores_non_accum_purpose(tmp_path: Path):
    db = tmp_path / "preopen.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        (
            "o1",
            "PRE_OPEN_AUCTION_DIRECTION",
            _payload(session="2026-06-02", risk_snap="2026-07-28"),
        ),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.row_count == 0
    assert raw.risk_snapshot_after_session_count == 0


def test_learning_risk_pit_gate_mismatch(tmp_path: Path):
    db = tmp_path / "gate.db"
    conn = sqlite3.connect(db)
    _create_learning_observations(conn)
    conn.execute(
        "INSERT INTO learning_observations VALUES (?, ?, ?)",
        (
            "o1",
            "ACCUMULATION_DISCOVERY",
            _payload(
                session="2026-06-02",
                risk_snap="2026-06-02",
                gate_snap="2026-06-05",
            ),
        ),
    )
    conn.commit()
    conn.close()

    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.gate_context_session_mismatch_count == 1
    assert raw.risk_snapshot_after_session_count == 0


def test_learning_risk_pit_missing_table(tmp_path: Path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    raw = SQLiteSignalArtifactReconciliationReader(db).observe_learning_observations_risk_pit()
    assert raw.exists is False


# ── read-only / no-mutation guarantees ───────────────────────────────────


def test_reader_does_not_mutate_database(full_schema_db: Path):
    row_count_before = _row_count(full_schema_db, "candidate_observations")
    mtime_before = full_schema_db.stat().st_mtime_ns

    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)
    reader.observe_candidate_observations_identity()
    reader.observe_signal_forward_labels_linkage()
    reader.observe_market_context_snapshot_identity()
    reader.observe_regime_observations_identity()
    reader.observe_learning_observations_risk_pit()

    assert _row_count(full_schema_db, "candidate_observations") == row_count_before
    assert full_schema_db.stat().st_mtime_ns == mtime_before


def test_reader_opens_connection_in_read_only_mode(full_schema_db: Path, monkeypatch):
    reader = SQLiteSignalArtifactReconciliationReader(full_schema_db)

    real_connect = sqlite3.connect
    captured_uris: list[str] = []

    def spying_connect(database, *args, **kwargs):
        if kwargs.get("uri"):
            captured_uris.append(database)
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spying_connect)

    reader.observe_candidate_observations_identity()

    assert captured_uris, "expected a uri=True read-only connection"
    assert all("mode=ro" in uri for uri in captured_uris)

    with real_connect(f"file:{full_schema_db}?mode=ro", uri=True) as ro_conn:
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("INSERT INTO candidate_observations (ticker) VALUES ('X')")


def _row_count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()
