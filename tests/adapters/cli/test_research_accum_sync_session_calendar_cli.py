"""CLI-level tests for research accum sync-session-calendar and conflict paths."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.application.dto.accumulation_structural_filter import StructuralFilterDecision
from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS_V4,
    AccumPopulationBinding,
    AssessmentPurpose,
    LearningContractId,
    LearningObservation,
    ProductionPolicySnapshot,
    stamp_universe_membership_id,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_trading_session_calendar_snapshot_repository import (
    SQLiteTradingSessionCalendarSnapshotRepository,
)

runner = CliRunner()
NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
COMPAT = "sha256:" + ("ee" * 32)
MEMBERSHIP = ["BBCA", "BBRI"]
NAMED = ["ASII", "BBCA", "BBRI", "BMRI", "TLKM"]
UNIVERSE = stamp_universe_membership_id(MEMBERSHIP)
MATERIAL = "sha256:" + ("33" * 32)


def _weekdays(start: date, end: date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _observation(db_day: int = 1, ticker: str = "BBCA") -> LearningObservation:
    sd = f"2026-07-{db_day:02d}"
    at = datetime(2026, 7, db_day, 12, 0, tzinfo=timezone.utc)
    binding = AccumPopulationBinding.create(
        membership_tickers=MEMBERSHIP,
        named_universe_tickers=NAMED,
        membership_session=sd,
        pit_tradable_lookback_sessions=10,
        producer_source_revision="test",
    )
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=at,
        universe_id=UNIVERSE,
        window_id=f"{ticker}:{sd}",
        decision_payload={
            "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            "artifact_type": "accumulation_session_observation",
            "ticker": ticker,
            "session_date": sd,
            "captured_at": at.isoformat(),
            "canonical_window": 7,
            "workflow": "research_accum_capture",
            "horizon_primary": "accum_10d",
            "shared": {
                "current_price": 100.0,
                "provenance": {
                    "decision_at": at.isoformat(),
                    "latest_completed_session": sd,
                    "analysis_as_of": sd,
                    "market_session_name": "regular",
                    "is_eod_pending": False,
                },
            },
            "features_by_window": {
                "7": {
                    "structural_filter": StructuralFilterDecision.disabled().to_dict(),
                    "trade_setup": {"action": "WATCH"},
                    "signal": {},
                    "candidate": {},
                },
                "30": {
                    "structural_filter": StructuralFilterDecision.disabled().to_dict(),
                    "trade_setup": {"action": "WATCH"},
                    "signal": {},
                    "candidate": {},
                },
                "90": {
                    "structural_filter": StructuralFilterDecision.disabled().to_dict(),
                    "trade_setup": {"action": "WATCH"},
                    "signal": {},
                    "candidate": {},
                },
            },
            "population_binding": binding.to_dict(),
        },
        captured_at=at,
        producer_source_revision="ai-saham@test",
    )


def _seed_policy(repo: SQLiteLearningArtifactRepository) -> None:
    for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS_V4:
        d = ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4[policy_id]
        repo.add_policy_snapshot(
            ProductionPolicySnapshot.create(
                contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V4,
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
                producer_observation_contract="accumulation-discovery.v2",
                compatibility_id=COMPAT,
                policy_id=policy_id,
                policy_version=d.policy_version,
                decision_type=d.decision_type,
                semantic_engine_contract_id=d.semantic_engine_contract_id,
                material_config_hash=MATERIAL,
                canonical_payload={
                    "policy_id": policy_id,
                    "policy_version": d.policy_version,
                    "decision_type": d.decision_type,
                    "semantic_engine_contract_id": d.semantic_engine_contract_id,
                },
                source_revision="test",
                created_at=NOW,
            )
        )


class _FakeSession:
    authenticated = True

    class api_client:
        @staticmethod
        def get(url: str):
            dates = _weekdays(date(2026, 7, 1), date(2026, 8, 31))
            return {"data": {"result": [{"date": d} for d in dates]}}


def _patch_stockbit_ok(monkeypatch) -> None:
    class _Cfg:
        historical_summary_url = "https://example.test/history/{ticker}"

    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.load_stockbit_provider_config",
        lambda: _Cfg(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands._stockbit_session.get_stockbit_session",
        lambda cfg: _FakeSession(),
    )


def test_auto_no_op_without_stockbit_auth(tmp_path: Path, monkeypatch) -> None:
    """Empty corpus: --auto returns no-op without requiring Stockbit login."""
    db = tmp_path / "empty.db"
    # Create learning DB with zero observations
    SQLiteLearningArtifactRepository(db)

    # If auth is consulted, fail hard.
    def _deny(cfg):
        raise AssertionError("Stockbit must not be contacted for auto no-op")

    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands.load_stockbit_provider_config",
        lambda: object(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_evaluate_commands._stockbit_session.get_stockbit_session",
        _deny,
    )

    result = runner.invoke(
        app,
        [
            "research",
            "accum",
            "sync-session-calendar",
            "--auto",
            "--end",
            "2026-07-31",
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["no_op"] is True
    assert payload["no_op_reason"] == "no_current_schema_observations"
    # Snapshot table must not be created by no-op path.
    with sqlite3.connect(str(db)) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "trading_session_calendar_snapshots" not in tables


def test_invalid_end_date_exits_nonzero(tmp_path: Path) -> None:
    db = tmp_path / "does-not-exist-yet.db"
    assert not db.exists()
    result = runner.invoke(
        app,
        [
            "research",
            "accum",
            "sync-session-calendar",
            "--start",
            "2026-07-01",
            "--end",
            "not-a-date",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code != 0
    assert not db.exists(), "invalid manual args must not create the database"


def test_invalid_start_after_end_creates_no_db(tmp_path: Path) -> None:
    db = tmp_path / "bad-range.db"
    assert not db.exists()
    result = runner.invoke(
        app,
        [
            "research",
            "accum",
            "sync-session-calendar",
            "--start",
            "2026-08-01",
            "--end",
            "2026-07-01",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code != 0
    assert not db.exists()


def _seed_chain_corpus(db: Path) -> None:
    """Shared setup for sync → labels → status CLI verticals."""
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(1, "BBCA")
    o2 = _observation(2, "BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
    _seed_policy(repo)

    market = SQLiteMarketRepository(db)
    days = [date.fromisoformat(d) for d in _weekdays(date(2026, 7, 1), date(2026, 8, 31))]
    candles = []
    for t in ("BBCA", "BBRI"):
        for d in days:
            candles.append(
                Candle(
                    ticker=t,
                    date=d,
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("99"),
                    close=Decimal("101"),
                    volume=1000,
                )
            )
    market.save_candles(candles)
    from src.domain.value_objects.corporate_action_calendar import CorporateActionType
    from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
        SQLiteCorporateActionCalendarRepository,
    )

    ca = SQLiteCorporateActionCalendarRepository(db)
    ca.mark_synced(
        sync_date=date(2026, 7, 31),
        event_types=(CorporateActionType.STOCK_SPLIT,),
        status="success",
        source="stockbit",
    )


def test_cli_sync_labels_status_chain(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "chain.db"
    _seed_chain_corpus(db)
    _patch_stockbit_ok(monkeypatch)

    sync = runner.invoke(
        app,
        [
            "research",
            "accum",
            "sync-session-calendar",
            "--start",
            "2026-07-01",
            "--end",
            "2026-08-31",
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert sync.exit_code == 0, sync.output
    sync_payload = json.loads(sync.output)
    assert sync_payload["inserted"] is True
    snapshot_id = sync_payload["snapshot_id"]

    labels = runner.invoke(
        app,
        [
            "research",
            "accum",
            "labels",
            "--label-contract",
            "price_path.accum_10d.v1",
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert labels.exit_code == 0, labels.output
    label_payload = json.loads(labels.output)
    assert label_payload["inserted_count"] >= 1

    before = db.stat()
    status = runner.invoke(
        app,
        ["research", "accum", "status", "--db", str(db), "--format", "json"],
    )
    after = db.stat()
    assert status.exit_code == 0, status.output
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
    status_payload = json.loads(status.output)
    assert status_payload["artifact_type"] == "accumulation_producer_readiness"
    # Vertical with full H10 candles + snapshot must be READY — not a soft set.
    assert status_payload["cohorts"][0]["producer_status"] == "CHALLENGE_INPUT_READY"
    stored = SQLiteTradingSessionCalendarSnapshotRepository(db).get_snapshot(snapshot_id)
    assert stored is not None


def test_cli_auto_sync_labels_status_chain(tmp_path: Path, monkeypatch) -> None:
    """Cron path uses --auto; must reach CHALLENGE_INPUT_READY end-to-end."""
    db = tmp_path / "auto-chain.db"
    _seed_chain_corpus(db)
    _patch_stockbit_ok(monkeypatch)

    sync = runner.invoke(
        app,
        [
            "research",
            "accum",
            "sync-session-calendar",
            "--auto",
            "--end",
            "2026-08-31",
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert sync.exit_code == 0, sync.output
    sync_payload = json.loads(sync.output)
    assert sync_payload["no_op"] is False
    assert sync_payload["inserted"] is True

    labels = runner.invoke(
        app,
        [
            "research",
            "accum",
            "labels",
            "--label-contract",
            "price_path.accum_10d.v1",
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert labels.exit_code == 0, labels.output
    assert json.loads(labels.output)["inserted_count"] >= 1

    status = runner.invoke(
        app,
        ["research", "accum", "status", "--db", str(db), "--format", "json"],
    )
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["cohorts"][0]["producer_status"] == "CHALLENGE_INPUT_READY"


def _seed_pre_migration_authority_conflict(db: Path) -> None:
    """Insert dual natural-key rows without the unique index (corruption shape)."""
    import pytest

    from src.domain.value_objects.learning_artifacts import LearningContractError

    store = SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions_a = tuple(
        date.fromisoformat(d) for d in _weekdays(date(2026, 7, 1), date(2026, 7, 20))
    )
    sessions_b = sessions_a[:-1] + (date(2026, 7, 21),)
    a = TradingSessionCalendarSnapshot.create(
        coverage_start=date(2026, 7, 1),
        coverage_end=date(2026, 7, 31),
        ordered_sessions=sessions_a,
        source_revision="same-rev",
        captured_at=NOW,
    )
    store.add_snapshot(a)
    b = TradingSessionCalendarSnapshot.create(
        coverage_start=date(2026, 7, 1),
        coverage_end=date(2026, 7, 31),
        ordered_sessions=sessions_b,
        source_revision="same-rev",
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(LearningContractError, match="source conflict"):
        store.add_snapshot(b)

    payload = b.to_dict()
    with sqlite3.connect(str(db)) as conn:
        conn.execute("DROP INDEX IF EXISTS uq_trading_session_calendar_authority")
        conn.execute(
            """
            INSERT INTO trading_session_calendar_snapshots (
                snapshot_id, contract_id, source, benchmark,
                coverage_start, coverage_end, ordered_sessions_json,
                source_revision, captured_at, payload_digest, artifact_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                b.snapshot_id,
                b.contract_id,
                b.source,
                b.benchmark,
                b.coverage_start.isoformat(),
                b.coverage_end.isoformat(),
                json.dumps([s.isoformat() for s in b.ordered_sessions]),
                b.source_revision,
                b.captured_at.isoformat(),
                b.payload_digest,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        conn.commit()


def test_labels_exit_nonzero_on_calendar_source_conflict(tmp_path: Path) -> None:
    """Pre-migration dual natural-key rows fail schema open / labels (not ordinary skip)."""
    import pytest

    from src.domain.value_objects.learning_artifacts import LearningContractError

    db = tmp_path / "conflict.db"
    repo = SQLiteLearningArtifactRepository(db)
    repo.add_observation(_observation(1, "BBCA"))
    _seed_pre_migration_authority_conflict(db)

    # Write-repo open must refuse to migrate over dual authority rows.
    with pytest.raises(LearningContractError, match="migration integrity"):
        SQLiteTradingSessionCalendarSnapshotRepository(db)

    result = runner.invoke(
        app,
        [
            "research",
            "accum",
            "labels",
            "--label-contract",
            "price_path.accum_10d.v1",
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert result.exit_code != 0
    combined = (result.output + (result.stderr or "")).lower()
    assert "calendar source conflict" in combined or "migration integrity" in combined


def test_sync_cli_migration_conflict_controlled_diagnostic(tmp_path: Path, monkeypatch) -> None:
    """Pre-migration dual rows must not escape as an unhandled traceback."""
    db = tmp_path / "sync-migrate-conflict.db"
    SQLiteLearningArtifactRepository(db)
    _seed_pre_migration_authority_conflict(db)
    _patch_stockbit_ok(monkeypatch)

    result = runner.invoke(
        app,
        [
            "research",
            "accum",
            "sync-session-calendar",
            "--start",
            "2026-07-01",
            "--end",
            "2026-07-31",
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "calendar sync failed:" in combined
    assert "migration integrity" in combined.lower()
    # Controlled diagnostic: no Python traceback dumped to the operator.
    assert "Traceback" not in combined


def test_status_blocked_on_corrupt_snapshot_json(tmp_path: Path) -> None:
    db = tmp_path / "corrupt.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(1, "BBCA")
    o2 = _observation(2, "BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
    _seed_policy(repo)
    store = SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions = tuple(date.fromisoformat(d) for d in _weekdays(date(2026, 7, 1), date(2026, 8, 15)))
    snap = TradingSessionCalendarSnapshot.create(
        coverage_start=date(2026, 7, 1),
        coverage_end=date(2026, 8, 15),
        ordered_sessions=sessions,
        source_revision="r1",
        captured_at=NOW,
    )
    store.add_snapshot(snap)

    # Create labels bound to snap via domain use case (not full CLI labels).
    from src.application.use_case.database_learning_lifecycle_use_case import (
        GenerateAccumulationPricePathLabelsUseCase,
        GenerateLearningLabelsRequest,
    )

    market = SQLiteMarketRepository(db)
    candles = []
    for t in ("BBCA", "BBRI"):
        for d in sessions:
            candles.append(
                Candle(
                    ticker=t,
                    date=d,
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=10,
                )
            )
    market.save_candles(candles)
    gen = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=market,
        corporate_actions=type(
            "CA",
            (),
            {
                "has_any_sync_marker": lambda self: True,
                "get_events_for_ticker": lambda *a, **k: (),
            },
        )(),
        session_snapshot=snap,
    )
    gen.execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id=COMPAT,
            label_contract=LearningContractId.ACCUM_10D_LABEL,
            labeled_at=NOW,
        )
    )

    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "UPDATE trading_session_calendar_snapshots SET artifact_json = ? WHERE snapshot_id = ?",
            ("{broken", snap.snapshot_id),
        )
        conn.commit()

    status = runner.invoke(
        app,
        ["research", "accum", "status", "--db", str(db), "--format", "json"],
    )
    assert status.exit_code == 0, status.output
    payload = json.loads(status.output)
    assert payload["cohorts"][0]["producer_status"] == "BLOCKED_POLICY"


def test_cron_script_orders_sync_before_labels() -> None:
    root = Path(__file__).resolve().parents[3]
    wrapper = (root / "scripts" / "cron_accum_challenge_corpus.sh").read_text()
    sync_at = wrapper.index("sync-session-calendar")
    labels_at = wrapper.index("research accum labels")
    assert sync_at < labels_at
    # Conflict/failure must not emit COMPLETION_OK before status.
    assert wrapper.rindex("COMPLETION_OK") > wrapper.index("research accum status")
