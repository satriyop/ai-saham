"""Tests for intraday CLI commands."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.screen_commands import (
    DEFAULT_PRE_OPEN_CONFIG_PATH,
    _build_data_freshness,
    _build_intraday_run_guard,
    _format_market_regime,
    _market_regime_warning,
    _write_sidecar as write_pre_open_sidecar,
)
from src.application.use_case.market_regime import MarketRegimeResponse
from src.domain.entities.candle import Candle
from src.domain.value_objects.screener_result import ScreenerCandidate
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

runner = CliRunner()


class FakeRangeRepository:
    def __init__(self, ranges):
        self._ranges = ranges

    def get_date_range(self, ticker: str):
        return self._ranges.get(ticker)


def _candidate(ticker: str) -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        iev=150000,
        entry_price=Decimal("1000"),
        stop_loss_price=Decimal("950"),
        capital=Decimal("3000000"),
    )


def test_pre_open_guard_blocks_weekends_without_override():
    guard = _build_intraday_run_guard(
        datetime(2026, 6, 13, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta")),
        allow_non_trading_day=False,
    )

    assert guard.error is not None
    assert "weekend" in guard.error


def test_pre_open_guard_allows_weekend_dry_run_with_warning():
    guard = _build_intraday_run_guard(
        datetime(2026, 6, 13, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta")),
        allow_non_trading_day=True,
    )

    assert guard.error is None
    assert any("weekend" in warning for warning in guard.warnings)


def test_pre_open_guard_warns_outside_pre_open_window():
    guard = _build_intraday_run_guard(
        datetime(2026, 6, 12, 10, 15, tzinfo=ZoneInfo("Asia/Jakarta")),
        allow_non_trading_day=False,
    )

    assert guard.error is None
    assert any("outside IDX pre-open window" in warning for warning in guard.warnings)


def test_data_freshness_uses_oldest_latest_date_across_candidates():
    freshness = _build_data_freshness(
        candidates=[_candidate("BBCA"), _candidate("BUMI")],
        analysis_date=date(2026, 6, 13),
        market_repo=FakeRangeRepository({
            "BBCA": (date(2026, 1, 1), date(2026, 6, 12)),
            "BUMI": (date(2026, 1, 1), date(2026, 6, 10)),
        }),
        broker_repo=FakeRangeRepository({
            "BBCA": (date(2026, 1, 1), date(2026, 6, 12)),
            "BUMI": (date(2026, 1, 1), date(2026, 6, 11)),
        }),
    )

    assert freshness.analysis_date == date(2026, 6, 13)
    assert freshness.candle_end == date(2026, 6, 10)
    assert freshness.broker_end == date(2026, 6, 11)
    assert any("Latest candle" in warning for warning in freshness.warnings)
    assert any("Latest broker-flow" in warning for warning in freshness.warnings)
    assert any("differ" in warning for warning in freshness.warnings)


def test_default_pre_open_config_lives_under_config():
    assert DEFAULT_PRE_OPEN_CONFIG_PATH == Path("config/pre_open_screener.yaml")
    assert DEFAULT_PRE_OPEN_CONFIG_PATH.exists()


def test_pre_open_strategy_alias_is_deprecated():
    result = runner.invoke(
        app,
        [
            "intraday",
            "pre-open",
            "--movers-json",
            '[{"ticker":"BBCA","iev":150000}]',
            "--fast",
            "--strategy",
            str(DEFAULT_PRE_OPEN_CONFIG_PATH),
        ],
    )

    assert "Warning: --strategy is deprecated" in result.output


def test_market_regime_format_and_warning_are_intraday_context():
    response = MarketRegimeResponse(
        as_of_date=date(2026, 6, 12),
        label="WEAK",
        score=2,
        benchmark_ticker="^JKSE",
        benchmark_close=Decimal("7050"),
        benchmark_sma20=Decimal("7150"),
        benchmark_sma50=Decimal("7250"),
        benchmark_return_5d_pct=-1.25,
        benchmark_return_20d_pct=-4.75,
        breadth_above_sma20_pct=23.5294,
        breadth_change_5d_pct=-10.0,
        foreign_flow_breadth_pct=39.7059,
        universe_count=80,
        breadth_count=68,
        foreign_flow_count=68,
    )

    line = _format_market_regime(response)

    assert "REGIME: WEAK score=2/7" in line
    assert "^JKSE 20d -4.75%" in line
    assert "Breadth SMA20 23.53%" in line
    assert "Foreign breadth 39.71%" in line
    assert "reduce size" in _market_regime_warning(response)


def test_pre_open_sidecar_persists_market_regime_context(tmp_path):
    sidecar = tmp_path / "last-session.json"
    response = MarketRegimeResponse(
        as_of_date=date(2026, 6, 12),
        label="RISK_OFF",
        score=1,
        benchmark_ticker="^JKSE",
        benchmark_close=None,
        benchmark_sma20=None,
        benchmark_sma50=None,
        benchmark_return_5d_pct=None,
        benchmark_return_20d_pct=None,
        breadth_above_sma20_pct=20.0,
        breadth_change_5d_pct=-15.0,
        foreign_flow_breadth_pct=25.0,
        universe_count=80,
        breadth_count=70,
        foreign_flow_count=70,
    )

    write_pre_open_sidecar([_candidate("BBCA")], date(2026, 6, 12), sidecar, response)

    saved = json.loads(sidecar.read_text())
    assert saved["market_regime"]["label"] == "RISK_OFF"
    assert saved["market_regime"]["score"] == 1
    assert saved["candidates"][0]["ticker"] == "BBCA"


def _write_sidecar(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "screened_at": "2026-06-12",
                "candidates": [
                    {
                        "ticker": "BBCA",
                        "iev": 450000,
                        "gap_pct": "0.6",
                        "entry_range_low": "8800",
                        "entry_range_high": "9300",
                        "suggested_entry": "9050",
                        "atr_stop": "8900",
                        "trend": "BULLISH",
                        "rsi": "52",
                        "accum_tag": "BACKED",
                    },
                    {
                        "ticker": "GOTO",
                        "iev": 155000,
                        "gap_pct": "4.2",
                        "entry_range_low": "228",
                        "entry_range_high": "242",
                        "suggested_entry": "235",
                        "atr_stop": "221",
                        "trend": "BEARISH",
                        "rsi": "73",
                    },
                ],
            }
        )
    )


def test_confirm_open_outputs_decisions_and_writes_sidecar(tmp_path):
    session = tmp_path / "last-session.json"
    output = tmp_path / "last-confirmation.json"
    _write_sidecar(session)

    result = runner.invoke(
        app,
        [
            "intraday",
            "confirm-open",
            "--session",
            str(session),
            "--output",
            str(output),
            "--opening-json",
            '{"BBCA":9050,"GOTO":245}',
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION" in result.stdout
    assert "BBCA" in result.stdout
    assert "ENTER" in result.stdout
    assert "GOTO" in result.stdout
    assert "SKIP" in result.stdout

    saved = json.loads(output.read_text())
    assert saved["confirmed_at"] == "2026-06-12"
    assert saved["confirmations"][0]["decision"] == "ENTER"
    assert saved["confirmations"][1]["decision"] == "SKIP_GAP_UP"


def test_confirm_open_rejects_non_object_opening_json(tmp_path):
    session = tmp_path / "last-session.json"
    _write_sidecar(session)

    result = runner.invoke(
        app,
        [
            "intraday",
            "confirm-open",
            "--session",
            str(session),
            "--opening-json",
            '[{"BBCA":9050}]',
        ],
    )

    assert result.exit_code == 1
    assert "--opening-json must be a JSON object" in result.output


def test_intraday_confirm_open_works(tmp_path):
    session = tmp_path / "last-session.json"
    output = tmp_path / "last-confirmation.json"
    _write_sidecar(session)

    result = runner.invoke(
        app,
        [
            "intraday",
            "confirm-open",
            "--session",
            str(session),
            "--output",
            str(output),
            "--opening-json",
            '{"BBCA":9050}',
        ],
    )

    assert result.exit_code == 0, result.output
    assert "BBCA" in result.stdout
    assert "ENTER" in result.stdout


def test_confirm_log_appends_confirmation_sidecar(tmp_path):
    confirmation = tmp_path / "last-confirmation.json"
    journal = tmp_path / "confirmations.csv"
    confirmation.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [
                    {
                        "ticker": "BBCA",
                        "decision": "ENTER",
                        "opening_price": "9050",
                        "planned_entry": "9050",
                        "stop_loss_price": "8900",
                        "stop_pct": "1.7",
                        "reasons": ["open inside entry range"],
                        "iev": 450000,
                        "trend": "BULLISH",
                        "rsi": "52",
                        "gap_pct": "0.6",
                        "accum_tag": "BACKED",
                        "fvwap_discount_pct": "2.4",
                    }
                ],
            }
        )
    )

    result = runner.invoke(
        app,
        [
            "intraday",
            "confirm-log",
            "--confirmation",
            str(confirmation),
            "--journal",
            str(journal),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Logged 1 confirmation" in result.stdout
    assert "BBCA" in journal.read_text()


def test_confirm_review_outputs_bucket_tables(tmp_path):
    journal = tmp_path / "confirmations.csv"
    db_path = tmp_path / "data.db"

    confirmation = tmp_path / "last-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [
                    {
                        "ticker": "BBCA",
                        "decision": "ENTER",
                        "opening_price": "9050",
                        "planned_entry": "9050",
                        "stop_loss_price": "8900",
                        "stop_pct": "1.7",
                        "reasons": ["open inside entry range"],
                        "iev": 450000,
                        "trend": "BULLISH",
                        "rsi": "52",
                        "gap_pct": "0.6",
                        "accum_tag": "BACKED",
                        "fvwap_discount_pct": "2.4",
                    }
                ],
            }
        )
    )
    runner.invoke(
        app,
        [
            "intraday",
            "confirm-log",
            "--confirmation",
            str(confirmation),
            "--journal",
            str(journal),
        ],
    )

    repo = SQLiteMarketRepository(db_path=db_path)
    repo.save_candles(
        [
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 12),
                open=Decimal("9050"),
                high=Decimal("9225"),
                low=Decimal("9000"),
                close=Decimal("9200"),
                volume=1000000,
            )
        ]
    )

    result = runner.invoke(
        app,
        [
            "intraday",
            "confirm-review",
            "--journal",
            str(journal),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION REVIEW" in result.stdout
    assert "decision:ENTER" in result.stdout
    assert "gap:0-1" in result.stdout


def test_confirm_outcome_updates_logged_confirmation(tmp_path):
    journal = tmp_path / "confirmations.csv"
    confirmation = tmp_path / "last-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [
                    {
                        "ticker": "BBCA",
                        "decision": "ENTER",
                        "opening_price": "9050",
                        "planned_entry": "9050",
                        "stop_loss_price": "8900",
                        "stop_pct": "1.7",
                        "reasons": ["open inside entry range"],
                    }
                ],
            }
        )
    )
    runner.invoke(
        app,
        [
            "intraday",
            "confirm-log",
            "--confirmation",
            str(confirmation),
            "--journal",
            str(journal),
        ],
    )

    result = runner.invoke(
        app,
        [
            "intraday",
            "confirm-outcome",
            "BBCA",
            "--date",
            "2026-06-12",
            "--entry",
            "9050",
            "--exit",
            "9200",
            "--result",
            "target",
            "--notes",
            "manual exit",
            "--journal",
            str(journal),
            "--db",
            str(tmp_path / "data.db"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Recorded outcome for BBCA" in result.stdout
    assert "R=+1.00R" in result.stdout
    csv_text = journal.read_text()
    assert "manual exit" in csv_text
    assert "target" in csv_text
