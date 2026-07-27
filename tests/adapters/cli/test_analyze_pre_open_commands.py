"""CLI tests for saham analyze pre-open."""

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
        compatibility_id="compat-cli",
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


def test_analyze_pre_open_help() -> None:
    result = runner.invoke(app, ["analyze", "pre-open", "--help"])
    assert result.exit_code == 0
    assert "Post-open assessment of NCP pre-open plan" in result.stdout


def test_analyze_pre_open_json(tmp_path: Path) -> None:
    db = tmp_path / "learn.db"
    obs_id, snap_id = _seed(db)
    result = runner.invoke(
        app,
        [
            "analyze",
            "pre-open",
            "--session",
            SESSION.isoformat(),
            "--db",
            str(db),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["artifact_type"] == "analyze_pre_open_result"
    assert payload["status"] == "OK"
    assert payload["lines"][0]["post_open_action"] == "ENTER"
    assert payload["lines"][0]["observation_id"] == obs_id
    assert payload["lines"][0]["opening_snapshot_id"] == snap_id


def test_analyze_pre_open_missing_obs(tmp_path: Path) -> None:
    db = tmp_path / "learn.db"
    SQLiteLearningArtifactRepository(db)  # create empty schema
    result = runner.invoke(
        app,
        [
            "analyze",
            "pre-open",
            "--observation-id",
            "missing",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code == 1


def test_command_boundary_no_sidecar_writes() -> None:
    source = Path("src/adapters/cli/analyze_pre_open_commands.py").read_text(
        encoding="utf-8"
    )
    assert "write_intraday_confirmation" not in source
    assert "write_pre_open_sidecar" not in source
    assert "PreOpenPostOpenGatesUseCase" not in source
    assert "RunPreOpenPostOpenAssessmentWorkflowUseCase" not in source
