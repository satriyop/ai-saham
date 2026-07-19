from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.value_objects.signal_artifact_identity import (
    ArtifactId,
    ArtifactProvenance,
    ArtifactSourceProvenance,
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)


def test_save_and_get_signal_forward_label(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    label = SignalForwardLabel(
        ticker="bbca",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=10.0,
        max_forward_return=12.0,
        max_adverse_excursion=-2.0,
        days_to_peak=8,
        days_to_trough=2,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )

    repo.save_many([label])
    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)

    assert restored is not None
    assert restored.ticker == "BBCA"
    assert restored.entry_reference_price == Decimal("100")
    assert restored.outcome_label == SignalForwardOutcome.SUCCESS
    assert restored.target_would_trigger is True
    assert restored.stop_would_trigger is False
    assert restored.fingerprint.setup_family == "foreign_bounce"
    assert restored.fingerprint.market_regime == {"regime": "RISK_ON"}


def test_get_at_and_list_signal_forward_labels(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    day = date(2026, 7, 1)
    older = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=4.0)
    newer = _label(captured_at=datetime(2026, 7, 1, 10, 0, 0), close_return=5.0)
    repo.save_many([older, newer])

    exact = repo.get_at("bbca", day, SignalLabelHorizon.SWING_10D, older.observation_captured_at)
    latest = repo.get("bbca", day, SignalLabelHorizon.SWING_10D)
    listed = repo.list(signal_date=day, horizon=SignalLabelHorizon.SWING_10D, ticker="BBCA")

    assert exact is not None
    assert exact.close_return == 4.0
    assert latest is not None
    assert latest.close_return == 5.0
    assert [label.close_return for label in listed] == [5.0, 4.0]


def test_save_many_is_idempotent_for_same_observation(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    label = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=4.0)
    updated = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=5.0)

    repo.save_many([label])
    repo.save_many([updated])
    listed = repo.list(signal_date=date(2026, 7, 1), horizon=SignalLabelHorizon.SWING_10D)

    assert len(listed) == 1
    assert listed[0].close_return == 5.0


def test_schema_created_via_migration_runner(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteSignalForwardLabelsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        versions = conn.execute(
            "SELECT version FROM _schema_migrations WHERE namespace=?",
            ("signal_forward_labels",),
        ).fetchall()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

    assert {row[0] for row in versions} == set(range(12))
    assert "signal_forward_labels" in {row[0] for row in tables}


def test_effective_session_provenance_round_trips(tmp_path: Path):
    """DQ-002E: saving a label with provenance must round-trip every new
    field through SQLite exactly."""
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    label = _label(
        captured_at=datetime(2026, 7, 1, 9, 0, 0),
        close_return=4.0,
        decision_at=datetime(2026, 7, 1, 16, 0, 0),
        latest_completed_session=date(2026, 7, 1),
        analysis_as_of=date(2026, 7, 1),
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="ihsg_cache_same_day",
        resolution_notes=("note one", "note two"),
    )

    repo.save_many([label])
    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)

    assert restored is not None
    assert restored.decision_at == datetime(2026, 7, 1, 16, 0, 0)
    assert restored.latest_completed_session == date(2026, 7, 1)
    assert restored.analysis_as_of == date(2026, 7, 1)
    assert restored.market_session_name == "AFTER_CLOSE"
    assert restored.is_eod_pending is False
    assert restored.resolution_source == "ihsg_cache_same_day"
    assert restored.resolution_notes == ("note one", "note two")


def test_legacy_label_rows_with_no_provenance_read_as_none(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    label = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=4.0)

    repo.save_many([label])
    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)

    assert restored is not None
    assert restored.decision_at is None
    assert restored.latest_completed_session is None
    assert restored.analysis_as_of is None
    assert restored.market_session_name is None
    assert restored.is_eod_pending is None
    assert restored.resolution_source is None
    assert restored.resolution_notes == ()


def _sector_context_label(schema_version: int = 3) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=5.0,
        max_forward_return=5.0,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            alpha_trigger_route_metadata=({"group": "sector_context", "score": 75.0},),
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
        schema_version=schema_version,
    )


def test_repository_write_guard_rejects_in_memory_corrupted_current_label(tmp_path: Path):
    """SECTOR-CONTEXT-IDENTITY (Finding 1): the save_many defense-in-depth guard
    must reject a current label carrying the removed identity even when it
    reaches the repository past the construction guard. Simulate in-memory
    corruption by mutating the frozen fingerprint, then assert the write raises
    and persists zero rows."""
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)

    corrupt_label = _sector_context_label(schema_version=3)
    object.__setattr__(
        corrupt_label.fingerprint,
        "alpha_trigger_route_metadata",
        ({"group": "market_context", "score": 75.0},),
    )

    with pytest.raises(ValueError, match="removed Alpha/Trigger group 'market_context'"):
        repo.save_many([corrupt_label])

    assert tuple(repo.list()) == ()


def test_raw_inserted_current_label_with_removed_identity_fails_on_read(tmp_path: Path):
    """A current label row smuggled directly into the table (bypassing the
    write/construction guards) must still fail closed on read — the reader does
    not trust stored fingerprint contents."""
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    repo.save_many([_sector_context_label(schema_version=3)])

    corrupt_fingerprint = json.dumps(
        {"alpha_trigger_route_metadata": [{"group": "market_context", "score": 75.0}]}
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE signal_forward_labels SET fingerprint_json = ? WHERE ticker = 'BBCA'",
            (corrupt_fingerprint,),
        )
        conn.commit()

    with pytest.raises(ValueError, match="removed Alpha/Trigger group 'market_context'"):
        list(repo.list())


def test_current_label_malformed_flow_coverage_fails_on_write(tmp_path: Path):
    repo = SQLiteSignalForwardLabelsRepository(tmp_path / "data.db")
    label = _sector_context_label(schema_version=3)
    object.__setattr__(label.fingerprint, "flow_component_coverage", 1.0)
    object.__setattr__(label.fingerprint, "flow_missing_components", ("vwap",))

    with pytest.raises(ValueError, match="full flow coverage with missing components"):
        repo.save_many([label])

    assert tuple(repo.list()) == ()


def test_current_label_malformed_flow_coverage_fails_on_read(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    repo.save_many([_sector_context_label(schema_version=3)])
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE signal_forward_labels SET fingerprint_json = ? WHERE ticker = 'BBCA'",
            (
                json.dumps(
                    {
                        "flow_component_coverage": 0.5,
                        "flow_missing_components": ["unknown_component"],
                    }
                ),
            ),
        )
        conn.commit()

    with pytest.raises(ValueError, match="unknown flow_missing_components"):
        list(repo.list())


def _label(
    *,
    captured_at: datetime,
    close_return: float,
    decision_at: datetime | None = None,
    latest_completed_session: date | None = None,
    analysis_as_of: date | None = None,
    market_session_name: str | None = None,
    is_eod_pending: bool | None = None,
    resolution_source: str | None = None,
    resolution_notes: tuple[str, ...] = (),
) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=close_return,
        max_forward_return=close_return,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=captured_at,
        decision_at=decision_at,
        latest_completed_session=latest_completed_session,
        analysis_as_of=analysis_as_of,
        market_session_name=market_session_name,
        is_eod_pending=is_eod_pending,
        resolution_source=resolution_source,
        resolution_notes=resolution_notes,
    )


def test_signal_forward_label_benchmark_excess_return_round_trips(tmp_path: Path):
    from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturn, BenchmarkExcessReturnStatus
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)

    r5 = BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=5,
        ticker_return_pct=10.0,
        benchmark_return_pct=2.0,
        excess_return_pct=8.0,
        window_start=date(2026, 7, 10),
        window_end=date(2026, 7, 17),
        common_session_count=6,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
    )
    r20 = BenchmarkExcessReturn.unavailable(
        benchmark="IHSG",
        window_sessions=20,
        reason="insufficient_aligned_closes",
        common_session_count=15,
    )

    label = SignalForwardLabel(
        ticker="bbca",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=10.0,
        max_forward_return=12.0,
        max_adverse_excursion=-2.0,
        days_to_peak=8,
        days_to_trough=2,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            benchmark_excess_return_5_session=r5,
            benchmark_excess_return_20_session=r20,
            benchmark_excess_return_authority_status="DIAGNOSTIC_UNVALIDATED",
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )

    repo.save_many([label])
    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)

    assert restored is not None
    assert restored.fingerprint.benchmark_excess_return_5_session == r5
    assert restored.fingerprint.benchmark_excess_return_20_session == r20
    assert restored.fingerprint.benchmark_excess_return_authority_status == "DIAGNOSTIC_UNVALIDATED"


def test_sqlite_persistence_canonical_only(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)

    label = SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=10.0,
        max_forward_return=12.0,
        max_adverse_excursion=-2.0,
        days_to_peak=8,
        days_to_trough=2,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            # Legacy fields
            coverage=0.8,
            conviction=0.8,
            phase_strength=0.7,
            phase_coverage_score=0.6,
            phase_conviction_score=0.4,
            # Canonical replacement fields
            signal_authority_coverage=0.75,
            setup_readiness_status="READY",
            setup_readiness_current_phase="ACCUMULATION",
            setup_readiness_missing_required_inputs=("input1",),
            setup_readiness_failed_requirements=("req1",),
            phase_detection_strength=0.85,
            phase_input_coverage=0.95,
            # Scoped metrics (must be preserved)
            ia_foreign_track_conviction=0.9,
            ia_foreign_track_coverage=0.85,
            strategy_conviction_score=0.7,
            strategy_coverage_score=0.6,
            cq_coverage_score=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
        schema_version=3,
    )

    repo.save_many([label])

    # Test D: SQLite Raw Persistence
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT fingerprint_json FROM signal_forward_labels WHERE ticker='BBCA' LIMIT 1"
        ).fetchone()

    assert row is not None
    import json
    raw_fingerprint = json.loads(row[0])

    # Assert the raw JSON:
    # - omits all five forbidden keys;
    forbidden_keys = [
        "coverage",
        "conviction",
        "phase_strength",
        "phase_coverage_score",
        "phase_conviction_score",
    ]
    for key in forbidden_keys:
        assert key not in raw_fingerprint

    # - includes canonical authority coverage and readiness;
    assert raw_fingerprint["signal_authority_coverage"] == 0.75
    assert raw_fingerprint["setup_readiness_status"] == "READY"
    assert raw_fingerprint["setup_readiness_current_phase"] == "ACCUMULATION"
    assert raw_fingerprint["setup_readiness_missing_required_inputs"] == ["input1"]
    assert raw_fingerprint["setup_readiness_failed_requirements"] == ["req1"]

    # - includes canonical phase metrics;
    assert raw_fingerprint["phase_detection_strength"] == 0.85
    assert raw_fingerprint["phase_input_coverage"] == 0.95

    # - includes representative scoped fields.
    assert raw_fingerprint["ia_foreign_track_conviction"] == 0.9
    assert raw_fingerprint["ia_foreign_track_coverage"] == 0.85
    assert raw_fingerprint["strategy_conviction_score"] == 0.7
    assert raw_fingerprint["strategy_coverage_score"] == 0.6
    assert raw_fingerprint["cq_coverage_score"] == 0.8

    # Test E: SQLite Canonical Round Trip
    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)
    assert restored is not None

    # Assert canonical values survive.
    assert restored.fingerprint.signal_authority_coverage == 0.75
    assert restored.fingerprint.setup_readiness_status == "READY"
    assert restored.fingerprint.setup_readiness_current_phase == "ACCUMULATION"
    assert restored.fingerprint.setup_readiness_missing_required_inputs == ("input1",)
    assert restored.fingerprint.setup_readiness_failed_requirements == ("req1",)
    assert restored.fingerprint.phase_detection_strength == 0.85
    assert restored.fingerprint.phase_input_coverage == 0.95

    # Assert the five legacy fields are None after round-trip because they were not persisted.
    assert restored.fingerprint.coverage is None
    assert restored.fingerprint.conviction is None
    assert restored.fingerprint.phase_strength is None
    assert restored.fingerprint.phase_coverage_score is None
    assert restored.fingerprint.phase_conviction_score is None


# ── ARTIFACT-IDENTITY Slice 4: label identity persistence ────────────────────


_VALID_SHA256 = "ab" * 32
_ALT_SHA256 = "cd" * 32
_ANOTHER_SHA256 = "ef" * 32
_VALID_ARTIFACT_ID = f"sha256:{_VALID_SHA256}"
_VALID_SEM_COMPAT_ID = f"sha256:{_ALT_SHA256}"
_ANOTHER_ARTIFACT_ID = f"sha256:{_ANOTHER_SHA256}"


def _make_provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        application_revision="abc123",
        complete_config_hash=_VALID_SHA256,
        complete_authority_registry_hash=_ALT_SHA256,
        universe_snapshot_id="snap_001",
        idx_calendar_version="v2",
        session_rule_version="v1",
        decision_at=datetime(2026, 7, 1, 16, 0, 0, tzinfo=timezone.utc),
        captured_at=datetime(2026, 7, 1, 16, 30, 0, 123456, tzinfo=timezone.utc),
        latest_completed_session=date(2026, 7, 1),
        analysis_as_of=date(2026, 7, 1),
        sources=(
            ArtifactSourceProvenance(
                source_family="candles",
                provider="stockbit",
                source_snapshot_id=None,
                observed_through=date(2026, 7, 1),
                available_at=datetime(2026, 7, 1, 15, 30, 0, tzinfo=timezone.utc),
                cutoff_at=None,
            ),
        ),
        invocation_command=None,
        invocation_actor=None,
    )


def test_artifact_identity_none_reads_as_none(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    label = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=4.0)
    assert label.artifact_identity is None

    repo.save_many([label])

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT artifact_id, semantic_compatibility_id, artifact_provenance_json "
            "FROM signal_forward_labels WHERE ticker='BBCA'"
        ).fetchone()
    assert row["artifact_id"] == ""
    assert row["semantic_compatibility_id"] == ""
    assert row["artifact_provenance_json"] == ""

    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)
    assert restored is not None
    assert restored.artifact_identity is None


def test_artifact_identity_round_trip(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)

    provenance = _make_provenance()
    identity = SignalArtifactIdentity(
        artifact_id=ArtifactId(_VALID_ARTIFACT_ID),
        semantic_compatibility_id=SemanticCompatibilityId(_VALID_SEM_COMPAT_ID),
        provenance=provenance,
    )
    label = SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=5.0,
        max_forward_return=8.0,
        max_adverse_excursion=-1.0,
        days_to_peak=3,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
        artifact_identity=identity,
    )

    repo.save_many([label])
    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)
    assert restored is not None
    assert restored.artifact_identity is not None
    assert restored.artifact_identity.artifact_id == ArtifactId(_VALID_ARTIFACT_ID)
    assert restored.artifact_identity.semantic_compatibility_id == SemanticCompatibilityId(_VALID_SEM_COMPAT_ID)
    assert restored.artifact_identity.provenance == provenance


def test_partial_identity_columns_fail_on_read(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteSignalForwardLabelsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO signal_forward_labels "
            "(ticker, signal_date, horizon, observation_captured_at, "
            "outcome_label, fingerprint_json, schema_version, created_at, updated_at, "
            "artifact_id, semantic_compatibility_id, artifact_provenance_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "BBCA", "2026-07-01", "SWING_10D", "2026-07-01T09:00:00",
                "SUCCESS", '{"v":1}', 2, "2026-07-16T00:00:00", "2026-07-16T00:00:00",
                _VALID_ARTIFACT_ID, "", "",
            ),
        )

    repo = SQLiteSignalForwardLabelsRepository(db_path)
    with pytest.raises(ValueError, match="Partial signal artifact identity"):
        repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)


def test_null_identity_columns_fail_on_read(tmp_path: Path):
    """Actual NULL in an identity column must raise ValueError on repo.read.

    Create table without NOT NULL on identity columns to simulate a corrupt
    or manually-tampered database, insert a row with NULL identity, then
    verify repo.get() fails closed.
    """
    db_path = tmp_path / "null_identity.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE _schema_migrations (namespace TEXT, version INTEGER, UNIQUE(namespace, version))")
    conn.execute(
        "INSERT INTO _schema_migrations (namespace, version) VALUES (?, ?)",
        ("signal_forward_labels", 11),
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS signal_forward_labels ("
        "id                       INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ticker                   TEXT    NOT NULL, "
        "signal_date              TEXT    NOT NULL, "
        "horizon                  TEXT    NOT NULL, "
        "observation_captured_at  TEXT    NOT NULL DEFAULT '', "
        "entry_reference_price    TEXT, "
        "label_window_start       TEXT, "
        "label_window_end         TEXT, "
        "close_return             REAL, "
        "max_forward_return       REAL, "
        "max_adverse_excursion    REAL, "
        "days_to_peak             INTEGER, "
        "days_to_trough           INTEGER, "
        "stop_would_trigger       INTEGER, "
        "target_would_trigger     INTEGER, "
        "outcome_label            TEXT    NOT NULL, "
        "unavailable_reason       TEXT, "
        "fingerprint_json         TEXT    NOT NULL, "
        "schema_version           INTEGER NOT NULL DEFAULT 1, "
        "created_at               TEXT    NOT NULL, "
        "updated_at               TEXT    NOT NULL, "
        "decision_at              TEXT    NOT NULL DEFAULT '', "
        "latest_completed_session TEXT    NOT NULL DEFAULT '', "
        "analysis_as_of           TEXT    NOT NULL DEFAULT '', "
        "market_session_name      TEXT    NOT NULL DEFAULT '', "
        "is_eod_pending           INTEGER, "
        "resolution_source        TEXT    NOT NULL DEFAULT '', "
        "resolution_notes_json    TEXT    NOT NULL DEFAULT '[]', "
        "artifact_id              TEXT, "
        "semantic_compatibility_id TEXT, "
        "artifact_provenance_json TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, "
        "outcome_label, fingerprint_json, schema_version, created_at, updated_at, "
        "artifact_id, semantic_compatibility_id, artifact_provenance_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "BBCA", "2026-07-01", "SWING_10D", "2026-07-01T09:00:00",
            "SUCCESS", '{"v":1}', 1, "2026-07-16T00:00:00", "2026-07-16T00:00:00",
            None, None, None,
        ),
    )
    conn.commit()
    conn.close()

    repo = SQLiteSignalForwardLabelsRepository(db_path)
    with pytest.raises(ValueError, match="is NULL"):
        repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)


def test_noncanonical_provenance_json_fails_on_read(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteSignalForwardLabelsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO signal_forward_labels "
            "(ticker, signal_date, horizon, observation_captured_at, "
            "outcome_label, fingerprint_json, schema_version, created_at, updated_at, "
            "artifact_id, semantic_compatibility_id, artifact_provenance_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "BBCA", "2026-07-01", "SWING_10D", "2026-07-01T09:00:00",
                "SUCCESS", '{"v":1}', 2, "2026-07-16T00:00:00", "2026-07-16T00:00:00",
                _VALID_ARTIFACT_ID, _VALID_SEM_COMPAT_ID, '{"noncanonical": true}',
            ),
        )

    repo = SQLiteSignalForwardLabelsRepository(db_path)
    with pytest.raises(ValueError, match="artifact_provenance_json"):
        repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)


def test_upsert_replaces_identity_columns(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)

    provenance_a = _make_provenance()
    identity_a = SignalArtifactIdentity(
        artifact_id=ArtifactId(_VALID_ARTIFACT_ID),
        semantic_compatibility_id=SemanticCompatibilityId(_VALID_SEM_COMPAT_ID),
        provenance=provenance_a,
    )
    label_a = SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=5.0,
        max_forward_return=8.0,
        max_adverse_excursion=-1.0,
        days_to_peak=3,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
        artifact_identity=identity_a,
    )

    repo.save_many([label_a])

    label_b = SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("200"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=10.0,
        max_forward_return=12.0,
        max_adverse_excursion=-2.0,
        days_to_peak=5,
        days_to_trough=2,
        stop_would_trigger=True,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.FAILURE,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.9,
            conviction=0.9,
            market_regime={"regime": "RISK_OFF"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )
    repo.save_many([label_b])

    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)
    assert restored is not None
    assert restored.close_return == 10.0
    assert restored.artifact_identity is None

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT artifact_id, semantic_compatibility_id, artifact_provenance_json "
            "FROM signal_forward_labels WHERE ticker='BBCA'"
        ).fetchone()
    assert row["artifact_id"] == ""
    assert row["semantic_compatibility_id"] == ""
    assert row["artifact_provenance_json"] == ""


def test_no_unique_index_on_artifact_id(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteSignalForwardLabelsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        indexes = conn.execute(
            "SELECT name FROM pragma_index_list('signal_forward_labels')"
        ).fetchall()

    for idx_row in indexes:
        idx_name = idx_row[0]
        with sqlite3.connect(str(db_path)) as conn:
            cols = conn.execute(
                "SELECT name FROM pragma_index_info(?)", (idx_name,)
            ).fetchall()
        col_names = {c[0] for c in cols}
        assert "artifact_id" not in col_names, (
            f"Index {idx_name} includes artifact_id"
        )


def test_migrations_0_to_11_registered(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteSignalForwardLabelsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        versions = {
            row[0]
            for row in conn.execute(
                "SELECT version FROM _schema_migrations WHERE namespace=?",
                ("signal_forward_labels",),
            )
        }
    assert versions == set(range(12))


def test_to_dict_unchanged_by_identity_metadata(tmp_path: Path):
    label_without = SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=5.0,
        max_forward_return=8.0,
        max_adverse_excursion=-1.0,
        days_to_peak=3,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )

    provenance = _make_provenance()
    identity = SignalArtifactIdentity(
        artifact_id=ArtifactId(_ANOTHER_ARTIFACT_ID),
        semantic_compatibility_id=SemanticCompatibilityId(_VALID_SEM_COMPAT_ID),
        provenance=provenance,
    )
    label_with = SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=5.0,
        max_forward_return=8.0,
        max_adverse_excursion=-1.0,
        days_to_peak=3,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
        artifact_identity=identity,
    )

    keys_without = set(label_without.to_dict().keys())
    keys_with = set(label_with.to_dict().keys())
    assert keys_without == keys_with, (
        "to_dict() keys differ when artifact_identity is set"
    )
    assert "artifact_identity" not in keys_with


def test_label_default_artifact_identity_is_none():
    label = SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=5.0,
        max_forward_return=8.0,
        max_adverse_excursion=-1.0,
        days_to_peak=3,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )
    assert label.artifact_identity is None


def test_legacy_label_migration_preserves_row_and_reads_none(tmp_path: Path):
    """Pre-Slice-4 label remains present after migrations 9-11 run, all three
    columns are empty, and repository read returns artifact_identity=None."""
    db_path = tmp_path / "legacy_migrate.db"

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE _schema_migrations (namespace TEXT, version INTEGER)")
    for v in range(9):
        conn.execute(
            "INSERT INTO _schema_migrations (namespace, version) VALUES (?, ?)",
            ("signal_forward_labels", v),
        )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS signal_forward_labels ("
        "id                       INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ticker                   TEXT    NOT NULL, "
        "signal_date              TEXT    NOT NULL, "
        "horizon                  TEXT    NOT NULL, "
        "observation_captured_at  TEXT    NOT NULL DEFAULT '', "
        "entry_reference_price    TEXT, "
        "label_window_start       TEXT, "
        "label_window_end         TEXT, "
        "close_return             REAL, "
        "max_forward_return       REAL, "
        "max_adverse_excursion    REAL, "
        "days_to_peak             INTEGER, "
        "days_to_trough           INTEGER, "
        "stop_would_trigger       INTEGER, "
        "target_would_trigger     INTEGER, "
        "outcome_label            TEXT    NOT NULL, "
        "unavailable_reason       TEXT, "
        "fingerprint_json         TEXT    NOT NULL, "
        "schema_version           INTEGER NOT NULL DEFAULT 1, "
        "created_at               TEXT    NOT NULL, "
        "updated_at               TEXT    NOT NULL, "
        "decision_at              TEXT    NOT NULL DEFAULT '', "
        "latest_completed_session TEXT    NOT NULL DEFAULT '', "
        "analysis_as_of           TEXT    NOT NULL DEFAULT '', "
        "market_session_name      TEXT    NOT NULL DEFAULT '', "
        "is_eod_pending           INTEGER, "
        "resolution_source        TEXT    NOT NULL DEFAULT '', "
        "resolution_notes_json    TEXT    NOT NULL DEFAULT '[]'"
        ")"
    )
    conn.execute(
        "INSERT OR IGNORE INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, "
        "outcome_label, fingerprint_json, schema_version, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "BBCA", "2026-07-01", "SWING_10D", "2026-07-01T09:00:00",
            "SUCCESS", '{"v":1}', 2, "2026-07-16T00:00:00", "2026-07-16T00:00:00",
        ),
    )
    conn.commit()
    conn.close()

    repo = SQLiteSignalForwardLabelsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        versions = {
            row[0]
            for row in conn.execute(
                "SELECT version FROM _schema_migrations WHERE namespace=?",
                ("signal_forward_labels",),
            ).fetchall()
        }
    assert versions == set(range(12))

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT artifact_id, semantic_compatibility_id, artifact_provenance_json "
            "FROM signal_forward_labels WHERE ticker='BBCA'"
        ).fetchone()
    assert row["artifact_id"] == ""
    assert row["semantic_compatibility_id"] == ""
    assert row["artifact_provenance_json"] == ""

    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)
    assert restored is not None
    assert restored.ticker == "BBCA"
    assert restored.artifact_identity is None
