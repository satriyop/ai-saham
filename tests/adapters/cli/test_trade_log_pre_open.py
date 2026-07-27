"""CLI tests for trade log --type pre-open and removed confirm/intraday routes."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
    LearningTrackSnapshot,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

WIB = ZoneInfo("Asia/Jakarta")
SESSION = date(2026, 6, 18)
runner = CliRunner()


def _seed(db: Path) -> tuple[str, str]:
    repo = SQLiteLearningArtifactRepository(db)
    obs = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="compat-log",
        cutoff_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
        universe_id="iev:2026-06-18",
        window_id="BBCA:2026-06-18",
        decision_payload={
            "ticker": "BBCA",
            "screen_result": "pass",
            "market_regime": {"regime": "NEUTRAL"},
            "candidate": {
                "ticker": "BBCA",
                "iev": 200_000,
                "entry_price": "10050",
                "stop_loss_price": "9800",
                "trend_signal": "BULLISH",
                "rsi": "52",
                "gap_pct": "1.0",
                "entry_range_low": "9900",
                "entry_range_high": "10100",
                "opening_broker_backing_tag": "BACKED",
            },
            "signal": {"direction": "BULLISH", "entry_quality": "ENTER", "score": 72},
            "trade_setup": {"action": "ENTER"},
        },
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )
    assert repo.add_observation(obs)
    snap = LearningTrackSnapshot.create(
        observation_id=obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 0, 10, tzinfo=WIB),
        source="stockbit.opening_track",
        snapshot_payload={
            "opening_price": "10050",
            "opening_price_source": "order_book_lastprice",
            "opening_price_confidence": "MEDIUM",
        },
        captured_at=datetime(2026, 6, 18, 9, 0, 10, tzinfo=WIB),
    )
    assert repo.add_track_snapshot(snap)
    return obs.observation_id, snap.snapshot_id


def test_trade_confirm_route_removed() -> None:
    result = runner.invoke(app, ["trade", "confirm", "--help"])
    assert result.exit_code != 0


def test_trade_review_pre_open_help() -> None:
    result = runner.invoke(app, ["trade", "review", "pre-open", "--help"])
    assert result.exit_code == 0


def test_trade_review_intraday_removed() -> None:
    result = runner.invoke(app, ["trade", "review", "intraday", "--help"])
    assert result.exit_code != 0


def test_trade_log_intraday_fails_closed() -> None:
    result = runner.invoke(app, ["trade", "log", "--type", "intraday"])
    assert result.exit_code == 1
    assert "pre-open" in (result.stdout + result.stderr).lower()


def test_trade_log_pre_open_requires_ids(tmp_path: Path) -> None:
    result = runner.invoke(app, ["trade", "log", "--type", "pre-open"])
    assert result.exit_code == 1
    assert "observation-id" in (result.stdout + result.stderr)


def test_trade_log_pre_open_writes_journal(tmp_path: Path) -> None:
    db = tmp_path / "learn.db"
    journal = tmp_path / "pre_open_journal.csv"
    obs_id, snap_id = _seed(db)
    result = runner.invoke(
        app,
        [
            "trade",
            "log",
            "--type",
            "pre-open",
            "--observation-id",
            obs_id,
            "--opening-snapshot-id",
            snap_id,
            "--db",
            str(db),
            "--journal",
            str(journal),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert journal.exists()
    text = journal.read_text(encoding="utf-8")
    assert "BBCA" in text
    assert "ENTER" in text

    # Idempotent
    result2 = runner.invoke(
        app,
        [
            "trade",
            "log",
            "--type",
            "pre-open",
            "--observation-id",
            obs_id,
            "--opening-snapshot-id",
            snap_id,
            "--db",
            str(db),
            "--journal",
            str(journal),
        ],
    )
    assert result2.exit_code == 0
    assert "Already logged" in result2.stdout or "no new rows" in result2.stdout.lower()

    jsonl = journal.parent / "trades.jsonl"
    assert jsonl.exists()
    row = json.loads(jsonl.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["trade_type"] == "pre-open"
    assert row["observation_id"] == obs_id
    assert row["opening_snapshot_id"] == snap_id
