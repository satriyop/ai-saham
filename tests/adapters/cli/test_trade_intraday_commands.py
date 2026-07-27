"""Tests for intraday trade CLI commands."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.trade_intraday_backtest_display import display_intraday_backtest
from src.application.use_case.intraday_backtest_use_case import IntradayBacktestResponse
from src.domain.entities.candle import Candle
from src.domain.entities.trade_tick import TradeTick
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

runner = CliRunner()


class _FakeIEVRepo:
    def __init__(self, db_path):
        pass

    def get_coverage(self):
        return {"total_dates": 0}


def _patch_intraday_proxy_dependencies(monkeypatch, captured: dict) -> None:
    from src.adapters.cli import trade_intraday_backtest_commands
    monkeypatch.setattr(
        trade_intraday_backtest_commands,
        "resolve_tickers",
        lambda universe, explicit, db_path, **kwargs: explicit or ["BBCA"],
    )
    monkeypatch.setattr(
        trade_intraday_backtest_commands,
        "SQLiteMarketRepository",
        lambda db_path: object(),
    )
    monkeypatch.setattr(
        trade_intraday_backtest_commands,
        "SQLiteBrokerRepository",
        lambda db_path: object(),
    )
    monkeypatch.setattr(
        trade_intraday_backtest_commands,
        "create_indicator_registry",
        lambda broker_repository, market_repository: object(),
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.sqlite_iev_repository.SQLiteIEVRepository",
        _FakeIEVRepo,
    )

    class FakeUseCase:
        def __init__(
            self,
            market_repository,
            broker_repository,
            indicator_registry,
            iev_repository=None,
        ):
            pass

        def execute(self, request):
            captured["request"] = request
            return IntradayBacktestResponse(
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.capital,
                cost_bps=request.cost_bps,
                include_wait=request.include_wait,
                max_daily_positions=request.max_daily_positions,
                final_equity=request.capital,
                total_return_pct=0.0,
                max_drawdown_pct=0.0,
                trade_count=0,
                win_rate_pct=None,
                avg_trade_return_pct=None,
                avg_winner_pct=None,
                avg_loser_pct=None,
                profit_factor=None,
                expectancy_pct=None,
                avg_r_multiple=None,
                exit_reason_counts={},
                decisions={},
                trading_days=0,
                days_with_trades=0,
                by_opening_broker_backing_tag=[],
                by_fvwap_sign=[],
                by_rsi_bucket=[],
                by_ticker=[],
                trades=[],
                warnings=[],
            )

    monkeypatch.setattr(trade_intraday_backtest_commands, "IntradayBacktestUseCase", FakeUseCase)



def test_intraday_backtest_display_calls_it_proxy_simulation(capsys):
    response = IntradayBacktestResponse(
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        initial_capital=Decimal("100000000"),
        cost_bps=Decimal("20"),
        include_wait=False,
        max_daily_positions=3,
        final_equity=Decimal("100000000"),
        total_return_pct=0.0,
        max_drawdown_pct=0.0,
        trade_count=1,
        win_rate_pct=100.0,
        avg_trade_return_pct=1.0,
        avg_winner_pct=1.0,
        avg_loser_pct=None,
        profit_factor=float("inf"),
        expectancy_pct=1.0,
        avg_r_multiple=1.0,
        exit_reason_counts={"target": 1},
        decisions={"ENTER": 1},
        trading_days=7,
        days_with_trades=1,
        by_opening_broker_backing_tag=[],
        by_fvwap_sign=[],
        by_rsi_bucket=[],
        by_ticker=[],
        trades=[],
        warnings=[],
    )

    display_intraday_backtest(response, show_trades=0)

    out = capsys.readouterr().out
    assert "INTRADAY PROXY SIMULATION" in out
    assert "daily OHLC" in out
    assert "saved NCP snapshots" in out
    assert "tick-friction and regime gates are not replayed" in out


def test_intraday_proxy_uses_pre_open_config_defaults(monkeypatch):
    captured: dict = {}
    _patch_intraday_proxy_dependencies(monkeypatch, captured)

    result = runner.invoke(
        app,
        [
            "trade", "backtest-intraday", "BBCA",
            "--start", "2026-06-01",
            "--end", "2026-06-01",
            "--format", "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["artifact_type"] == "intraday_proxy_simulation"
    request = captured["request"]
    assert request.atr_multiplier == Decimal("0.25")
    assert request.max_stop_pct == Decimal("0.07")
    assert request.rsi_overbought_threshold == Decimal("75")
    assert request.atr_range_cap_min == Decimal("0.01")
    assert request.atr_range_cap_max == Decimal("0.05")
    assert request.broker_backing_window_days == 7
    assert request.broker_backing_threshold == 50.0
    assert request.fvwap_period == 20
    assert request.history_days == 365


def test_intraday_proxy_cli_overrides_pre_open_config_defaults(monkeypatch):
    captured: dict = {}
    _patch_intraday_proxy_dependencies(monkeypatch, captured)

    result = runner.invoke(
        app,
        [
            "trade", "backtest-intraday", "BBCA",
            "--start", "2026-06-01",
            "--end", "2026-06-01",
            "--format", "json",
            "--atr-mult", "0.5",
            "--max-stop", "0.04",
            "--rsi-overbought", "70",
        ],
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    assert request.atr_multiplier == Decimal("0.5")
    assert request.max_stop_pct == Decimal("0.04")
    assert request.rsi_overbought_threshold == Decimal("70")


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
                        "opening_broker_backing_tag": "BACKED",
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


def _write_confirmation(path: Path, include_context: bool = False) -> None:
    row = {
        "ticker": "BBCA",
        "decision": "ENTER",
        "opening_price": "9050",
        "planned_entry": "9050",
        "stop_loss_price": "8900",
        "stop_pct": "1.7",
        "reasons": ["open inside entry range"],
    }
    if include_context:
        row.update(
            {
                "iev": 450000,
                "trend": "BULLISH",
                "rsi": "52",
                "gap_pct": "0.6",
                "opening_broker_backing_tag": "BACKED",
                "fvwap_discount_pct": "2.4",
            }
        )
    path.write_text(
        json.dumps(
            {
                "confirmed_at": "2026-06-12",
                "max_stop_pct": "0.07",
                "confirmations": [row],
            }
        )
    )



def test_trade_confirm_command_removed():
    """Clean break: post-open assess is analyze pre-open, not trade confirm."""
    result = runner.invoke(app, ["trade", "confirm", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output or "No such command" in (result.stdout + result.stderr)


def test_trade_log_intraday_type_removed():
    result = runner.invoke(app, ["trade", "log", "--type", "intraday"])
    assert result.exit_code == 1
    assert "pre-open" in (result.stdout + result.stderr).lower()


def test_confirm_review_pre_open_outputs_bucket_tables(tmp_path):
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )
    from src.domain.value_objects.intraday_confirmation import (
        IntradayConfirmationJournalEntry,
    )

    journal = tmp_path / "confirmations.csv"
    db_path = tmp_path / "data.db"
    store = IntradayConfirmationCsvStore(journal)
    store.append(
        [
            IntradayConfirmationJournalEntry(
                confirmed_at=date(2026, 6, 12),
                ticker="BBCA",
                decision="ENTER",
                reason_codes=("open inside entry range",),
                opening_price=Decimal("9050"),
                planned_entry=Decimal("9050"),
                stop_loss_price=Decimal("8900"),
                stop_pct=Decimal("1.7"),
                iev=450000,
                trend="BULLISH",
                rsi=Decimal("52"),
                gap_pct=Decimal("0.5"),
                opening_broker_backing_tag="BACKED",
            )
        ]
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
            "trade", "review", "pre-open",
            "--journal", str(journal),
            "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION REVIEW" in result.stdout
    assert "decision:ENTER" in result.stdout


def test_trade_outcome_updates_logged_confirmation(tmp_path):
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )
    from src.domain.value_objects.intraday_confirmation import (
        IntradayConfirmationJournalEntry,
    )

    journal = tmp_path / "confirmations.csv"
    store = IntradayConfirmationCsvStore(journal)
    store.append(
        [
            IntradayConfirmationJournalEntry(
                confirmed_at=date(2026, 6, 12),
                ticker="BBCA",
                decision="ENTER",
                reason_codes=("open inside entry range",),
                opening_price=Decimal("9050"),
                planned_entry=Decimal("9050"),
                stop_loss_price=Decimal("8900"),
                stop_pct=Decimal("1.7"),
            )
        ]
    )

    result = runner.invoke(
        app,
        [
            "trade", "outcome", "BBCA",
            "--date", "2026-06-12",
            "--entry", "9050",
            "--exit", "9200",
            "--result", "target",
            "--notes", "manual exit",
            "--journal", str(journal),
            "--db", str(tmp_path / "data.db"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Recorded outcome for BBCA" in result.stdout
    csv_text = journal.read_text()
    assert "manual exit" in csv_text
    assert "target" in csv_text
