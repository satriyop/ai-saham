"""Tests for intraday trade CLI commands."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

import src.adapters.cli.trade_intraday_commands as trade_intraday_commands
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
    monkeypatch.setattr(
        trade_intraday_commands,
        "resolve_tickers",
        lambda universe, explicit, db_path: explicit or ["BBCA"],
    )
    monkeypatch.setattr(
        trade_intraday_commands,
        "SQLiteMarketRepository",
        lambda db_path: object(),
    )
    monkeypatch.setattr(
        trade_intraday_commands,
        "SQLiteBrokerRepository",
        lambda db_path: object(),
    )
    monkeypatch.setattr(
        trade_intraday_commands,
        "create_indicator_registry",
        lambda broker_repository, market_repository: object(),
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.sqlite_iev_repository.SQLiteIEVRepository",
        _FakeIEVRepo,
    )

    class FakeUseCase:
        def __init__(self, market_repository, broker_repository, indicator_registry, iev_repository=None):
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

    monkeypatch.setattr(trade_intraday_commands, "IntradayBacktestUseCase", FakeUseCase)


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


def test_confirm_open_outputs_decisions_and_writes_sidecar(tmp_path):
    session = tmp_path / "last-session.json"
    output = tmp_path / "last-confirmation.json"
    _write_sidecar(session)

    result = runner.invoke(
        app,
        [
            "trade", "confirm",
            "--session", str(session),
            "--output", str(output),
            "--opening-json", '{"BBCA":9050,"GOTO":245}',
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION" in result.stdout
    assert "BBCA" in result.stdout
    assert "ENTER" in result.stdout
    assert "GOTO" in result.stdout
    assert "SKIP" in result.stdout

    saved = json.loads(output.read_text())
    assert saved["schema_version"] == 1
    assert saved["artifact_type"] == "intraday_confirmation"
    assert saved["confirmed_at"] == "2026-06-12"
    assert saved["confirmations"][0]["decision"] == "ENTER"
    assert saved["confirmations"][1]["decision"] == "SKIP_GAP_UP"


def test_confirm_open_rejects_non_object_opening_json(tmp_path):
    session = tmp_path / "last-session.json"
    _write_sidecar(session)

    result = runner.invoke(
        app,
        [
            "trade", "confirm",
            "--session", str(session),
            "--opening-json", '[{"BBCA":9050}]',
        ],
    )

    assert result.exit_code == 1
    assert "--opening-json must be a JSON object" in result.output


def test_intraday_confirm_open_auto_uses_stockbit_provider_stubs(tmp_path, monkeypatch):
    session = tmp_path / "last-session.json"
    output = tmp_path / "last-confirmation.json"
    _write_sidecar(session)

    class FakeBrokerProvider:
        def __init__(self, *args, **kwargs):
            pass

        def is_authenticated(self):
            return True

    class FakeRunningTradeProvider:
        def __init__(self, api_client):
            pass

        def fetch_running_trade(self, ticker: str, limit: int = 80):
            if ticker != "BBCA":
                return []
            return [
                TradeTick(
                    ticker="BBCA",
                    timestamp=datetime(2026, 6, 12, 9, 1, tzinfo=ZoneInfo("Asia/Jakarta")),
                    price=9050,
                    lot=10,
                    buyer_broker_code="AK",
                    seller_broker_code="YP",
                    trade_type="RG",
                )
            ]

    class FakeOrderBookProvider:
        def __init__(self, api_client):
            pass

        def fetch_snapshot(self, ticker: str):
            return None

    import src.infrastructure.browser.playwright_stockbit_provider as playwright_stockbit
    import src.infrastructure.browser.stockbit_order_book as stockbit_order_book
    import src.infrastructure.browser.stockbit_running_trade as stockbit_running_trade

    monkeypatch.setattr(playwright_stockbit, "StockbitBrokerProvider", FakeBrokerProvider)
    monkeypatch.setattr(
        stockbit_running_trade,
        "StockbitRunningTradeProvider",
        FakeRunningTradeProvider,
    )
    monkeypatch.setattr(stockbit_order_book, "StockbitOrderBookProvider", FakeOrderBookProvider)

    result = runner.invoke(
        app,
        [
            "trade", "confirm",
            "--session", str(session),
            "--output", str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Confirming 2 pre-open candidate(s)" in result.stdout
    assert "Resolving missing opening prices from Stockbit: BBCA, GOTO" in result.stdout
    assert "[1/2] BBCA: 9,050 via running_trade_first_tick/HIGH" in result.stdout
    assert "[2/2] GOTO: unresolved - no regular-board trade tick at or after 09:00" in result.stdout
    assert "Opening prices resolved: 1/2" in result.stdout
    assert "Unresolved opening prices:" in result.stdout
    assert "GOTO: no regular-board trade tick at or after 09:00" in result.stdout
    saved = json.loads(output.read_text())
    first = saved["confirmations"][0]
    assert first["ticker"] == "BBCA"
    assert first["opening_price"] == "9050"
    assert first["opening_price_source"] == "running_trade_first_tick"
    assert first["opening_price_confidence"] == "HIGH"
    assert first["auto_confirmed"] is True
    assert first["manual_override"] is False


def test_trade_log_intraday_writes_confirmation_sidecar(tmp_path):
    confirmation = tmp_path / "last-confirmation.json"
    journal = tmp_path / "confirmations.csv"
    _write_confirmation(confirmation)

    result = runner.invoke(
        app,
        [
            "trade", "log", "--type", "intraday",
            "--confirmation", str(confirmation),
            "--journal", str(journal),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Logged 1 confirmation" in result.stdout
    assert "BBCA" in journal.read_text()


def test_confirm_review_outputs_bucket_tables(tmp_path):
    journal = tmp_path / "confirmations.csv"
    db_path = tmp_path / "data.db"
    confirmation = tmp_path / "last-confirmation.json"
    _write_confirmation(confirmation, include_context=True)

    runner.invoke(
        app,
        [
            "trade", "log", "--type", "intraday",
            "--confirmation", str(confirmation),
            "--journal", str(journal),
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
            "trade", "review", "intraday",
            "--journal", str(journal),
            "--db", str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "INTRADAY CONFIRMATION REVIEW" in result.stdout
    assert "decision:ENTER" in result.stdout
    assert "gap:0-1" in result.stdout


def test_trade_outcome_updates_logged_confirmation(tmp_path):
    journal = tmp_path / "confirmations.csv"
    confirmation = tmp_path / "last-confirmation.json"
    _write_confirmation(confirmation)
    runner.invoke(
        app,
        [
            "trade", "log", "--type", "intraday",
            "--confirmation", str(confirmation),
            "--journal", str(journal),
        ],
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
    assert "R=+1.00R" in result.stdout
    csv_text = journal.read_text()
    assert "manual exit" in csv_text
    assert "target" in csv_text


def test_confirm_open_with_track_file(tmp_path):
    session = tmp_path / "last-session.json"
    output = tmp_path / "last-confirmation.json"
    track_file = tmp_path / "track_0900.json"
    _write_sidecar(session)

    # Let's write the track file
    track_file.write_text(json.dumps({
        "captured_at": "2026-06-12T09:00:05+07:00",
        "tickers": {
            "BBCA": {
                "mid_price": 9000,
                "order_book": {
                    "last_price": 9050,
                    "bid_pressure_ratio": 0.7,
                    "fnet_intraday": 1000000,
                }
            },
            "GOTO": {
                "mid_price": 245,
                "order_book": {
                    "last_price": 245,
                }
            }
        }
    }))

    result = runner.invoke(
        app,
        [
            "trade", "confirm",
            "--session", str(session),
            "--output", str(output),
            "--track-file", str(track_file),
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
