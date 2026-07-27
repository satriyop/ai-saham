"""Phase 2E command smoke matrix for key user-facing workflows."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

import src.adapters.cli.screen_pre_open_commands as screen_pre_open_commands
from src.adapters.cli.main import app
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from tests.integration.conftest import generate_test_candles

runner = CliRunner()


def _tx(code: str, buy: str = "70000000", sell: str = "20000000") -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
        broker_type=BrokerType.FOREIGN,
        buy_lot=700,
        sell_lot=200,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _broker_summary(ticker: str, day: date) -> BrokerSummary:
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(_tx("AK"),),
        top_sellers=(_tx("BK", buy="10000000", sell="30000000"),),
        foreign_buy_value=Decimal("120000000"),
        foreign_sell_value=Decimal("50000000"),
        foreign_buy_lot=1200,
        foreign_sell_lot=500,
        total_value=Decimal("500000000"),
        total_lot=5000,
        source="idx",
    )


def _seed_db(tmp_path: Path, ticker: str = "BBCA") -> Path:
    db_path = tmp_path / "data.db"
    start = date(2026, 1, 1)
    candles = generate_test_candles(
        days=180,
        start_price=Decimal("1000"),
        ticker=ticker,
        start_date=start,
    )
    market_repo = SQLiteMarketRepository(db_path=db_path)
    market_repo.save_candles(candles)
    broker_repo = SQLiteBrokerRepository(db_path)
    broker_repo.save_broker_summaries([
        _broker_summary(ticker, candle.date)
        for candle in candles[-40:]
    ])
    return db_path


def _json_stdout(result) -> dict:
    assert result.stdout.lstrip().startswith("{"), result.stdout
    return json.loads(result.stdout)


def test_plan_swing_table_and_json_contracts(temp_workspace, monkeypatch):
    monkeypatch.chdir(temp_workspace)
    db_path = _seed_db(temp_workspace)

    table = runner.invoke(
        app,
        ["plan", "swing", "BBCA", "--no-refresh", "--db", str(db_path)],
    )
    assert table.exit_code == 0, table.output
    assert "Swing Analysis - BBCA" in table.stdout
    assert "Verdict" in table.stdout
    assert "Candidate Actions" not in table.stdout

    js = runner.invoke(
        app,
        [
            "plan", "swing", "BBCA",
            "--no-refresh",
            "--format", "json",
            "--db", str(db_path),
        ],
    )
    assert js.exit_code == 0, js.output
    payload = _json_stdout(js)
    assert payload["artifact_type"] == "swing_analysis"
    assert payload["schema_version"] == 1
    assert payload["json_contract"]["canonical"] == ["verdict", "evidence", "diagnostics"]
    assert "compatibility_aliases" not in payload["json_contract"]
    for old_key in (
        "trade_setup",
        "signal_assessment",
        "risk",
        "accumulation",
        "setup",
        "strategy_evidence",
        "sentiment",
        "data",
        "flow_detail",
        "broker_detail",
        "broker_quality_note",
        "market_context_preview",
    ):
        assert old_key not in payload
    risk = payload["verdict"]["risk_assessment"]
    assert "risk_status" in risk
    assert "status" not in risk
    assert "level" not in risk
    accumulation = payload["evidence"]["accumulation"]
    assert "accum_score" in accumulation
    assert "score" not in accumulation
    assert "composite_foreign_flow_score" not in accumulation
    assert accumulation["foreign_flow_evidence"]["score_family"] == "composite_foreign_flow"


def _retired_screen_accum_pre_learning_json_contract(temp_workspace, monkeypatch):
    monkeypatch.chdir(temp_workspace)
    db_path = _seed_db(temp_workspace)

    table = runner.invoke(app, ["screen", "accum", "BBCA", "--db", str(db_path)])
    assert table.exit_code == 0, table.output
    assert "Candidate Actions" in table.stdout
    assert "Verdict" not in table.stdout

    js = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--format", "json", "--db", str(db_path)],
    )
    assert js.exit_code == 0, js.output
    payload = _json_stdout(js)
    assert payload["artifact_type"] == "accumulation_screen"
    assert payload["schema_version"] == 1
    assert payload["candidates"][0]["accum_score"] is not None
    assert "composite_foreign_flow_score" not in payload["candidates"][0]
    assert "risk_level" not in payload["candidates"][0]
    assert payload["candidates"][0]["foreign_flow_evidence"]["score_family"] == "composite_foreign_flow"

    multi = runner.invoke(app, ["screen", "accum", "BBCA", "--multi", "--db", str(db_path)])
    assert multi.exit_code == 0, multi.output
    assert "multi-window" in multi.stdout


def _retired_pre_open_file_sidecar_contract(temp_workspace, monkeypatch):
    db_path = _seed_db(temp_workspace)
    pre_open = runner.invoke(
        app,
        [
            "screen", "pre-open",
            "--movers-json", '[{"ticker":"BBCA","iev":150000}]',
            "--order-books-json", '{"BBCA":{"price":1000,"volume":50000}}',
            "--allow-non-trading-day",
            "--db", str(db_path),
        ],
    )
    assert pre_open.exit_code == 0, pre_open.output
    assert "PRE-OPEN OPENING SETUP" in pre_open.stdout
    assert "VERDICT:" not in pre_open.stdout

    # Database-identified post-open assess (replaces retired trade confirm sidecars)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.domain.value_objects.learning_artifacts import (
        AssessmentPurpose,
        LearningObservation,
        LearningTrackSnapshot,
    )
    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        SQLiteLearningArtifactRepository,
    )

    wib = ZoneInfo("Asia/Jakarta")
    learn = SQLiteLearningArtifactRepository(db_path)
    obs = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="smoke-compat",
        cutoff_at=datetime(2026, 6, 12, 8, 57, tzinfo=wib),
        universe_id="iev:2026-06-12",
        window_id="BBCA:2026-06-12",
        decision_payload={
            "ticker": "BBCA",
            "screen_result": "pass",
            "market_regime": {"regime": "NEUTRAL"},
            "candidate": {
                "ticker": "BBCA",
                "iev": 150000,
                "entry_price": "1000",
                "stop_loss_price": "950",
                "trend_signal": "BULLISH",
                "rsi": "55",
                "gap_pct": "1.0",
                "entry_range_low": "900",
                "entry_range_high": "1100",
                "opening_broker_backing_tag": "BACKED",
            },
            "signal": {"direction": "BULLISH", "entry_quality": "ENTER", "score": 72},
            "trade_setup": {"action": "ENTER"},
        },
        captured_at=datetime(2026, 6, 12, 8, 57, tzinfo=wib),
    )
    assert learn.add_observation(obs)
    assert learn.add_track_snapshot(
        LearningTrackSnapshot.create(
            observation_id=obs.observation_id,
            sampled_at=datetime(2026, 6, 12, 9, 0, 5, tzinfo=wib),
            source="stockbit.opening_track",
            snapshot_payload={
                "opening_price": "1000",
                "opening_price_source": "order_book_lastprice",
                "opening_price_confidence": "MEDIUM",
            },
            captured_at=datetime(2026, 6, 12, 9, 0, 5, tzinfo=wib),
        )
    )

    analyze = runner.invoke(
        app,
        [
            "assess", "pre-open",
            "--session", "2026-06-12",
            "--db", str(db_path),
            "--format", "json",
        ],
    )
    assert analyze.exit_code == 0, analyze.output
    payload = _json_stdout(analyze)
    assert payload["artifact_type"] == "assess_pre_open_result"
    assert payload["lines"][0]["post_open_action"] == "ENTER"


def test_backtest_json_contracts(temp_workspace, monkeypatch):
    db_path = _seed_db(temp_workspace)

    swing_bt = runner.invoke(
        app,
        [
            "backtest", "portfolio", "swing", "BBCA",
            "--start", "2026-06-01",
            "--end", "2026-06-20",
            "--format", "json",
            "--db", str(db_path),
        ],
    )
    assert swing_bt.exit_code == 0, swing_bt.output
    payload = _json_stdout(swing_bt)
    assert payload["artifact_type"] == "swing_backtest"

    # Retired: trade backtest-intraday (pre-open OHLC proxy CLI)
    retired = runner.invoke(app, ["trade", "backtest-intraday", "--help"])
    assert retired.exit_code != 0
