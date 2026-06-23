"""
CLI implementation functions for saham trade swing commands.

Public command registration lives in lifecycle routers:
  saham trade size
  saham trade backtest-swing

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_swing_display import display_swing_backtest
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.position_sizer import compute_position_size
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.swing_backtest_use_case import (
    DEFAULT_SWING_COST_BPS,
    SwingBacktestRequest,
    SwingBacktestUseCase,
)
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_PRESET as BACKTEST_FOREIGN_BOUNCE_PRESET,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


def _parse_regime_filter(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    regimes = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    valid = {"BULLISH", "SIDEWAYS", "WEAK", "RISK_OFF"}
    invalid = [regime for regime in regimes if regime not in valid]
    if invalid:
        raise typer.BadParameter(
            "--allow-regimes must contain only: BULLISH, SIDEWAYS, WEAK, RISK_OFF"
        )
    return regimes


# ─── swing backtest command ──────────────────────────────────────────────────

def swing_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
    ] = None,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Swing preset to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_PRESET,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = APP_CFG.trading.capital,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = APP_CFG.swing.risk_pct,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = 5,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = APP_CFG.swing.take_profit,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = APP_CFG.swing.stop_loss,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = APP_CFG.swing.max_hold,
    cost_bps: Annotated[
        float,
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = float(DEFAULT_SWING_COST_BPS),
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group trades by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to print", min=0),
    ] = 20,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Walk-forward backtest for the deterministic swing workflow.

    This validates the full daily process: scan, apply preset gates, rank
    candidates, open only within portfolio limits, avoid duplicate positions,
    and exit by TP/SL/max-hold. It reads local cached market and broker data.
    """
    preset_name = preset.lower()
    if preset_name != BACKTEST_FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. "
            f"Available presets: {BACKTEST_FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to backtest. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        allowed_regimes = _parse_regime_filter(allow_regimes)
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(
        f"Backtesting {len(ticker_list)} tickers | {start_date} to {end_date} | "
        f"preset={preset_name} | max positions={max_positions}..."
    )

    use_case = SwingBacktestUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    try:
        response = use_case.execute(SwingBacktestRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            preset=preset_name,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            max_positions=max_positions,
            take_profit_pct=Decimal(str(take_profit)),
            stop_loss_pct=Decimal(str(stop_loss)),
            max_hold_days=max_hold,
            cost_bps=Decimal(str(cost_bps)),
            include_regime=with_regime or bool(allowed_regimes),
            benchmark_ticker=benchmark,
            allowed_regimes=allowed_regimes,
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps({
            "preset": response.preset,
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "initial_capital": str(response.initial_capital),
            "cost_bps": str(response.cost_bps),
            "final_equity": str(response.final_equity),
            "total_return_pct": response.total_return_pct,
            "max_drawdown_pct": response.max_drawdown_pct,
            "trade_count": response.trade_count,
            "win_rate_pct": response.win_rate_pct,
            "avg_trade_return_pct": response.avg_trade_return_pct,
            "profit_factor": response.profit_factor,
            "exposure_pct": response.exposure_pct,
            "skipped_no_cash": response.skipped_no_cash,
            "skipped_duplicate": response.skipped_duplicate,
            "skipped_no_forward_data": response.skipped_no_forward_data,
            "skipped_by_regime": response.skipped_by_regime,
            "warnings": response.warnings,
            "regime_stats": [stat.to_dict() for stat in response.regime_stats],
            "regime_by_date": {
                key.isoformat(): value.to_dict()
                for key, value in response.regime_by_date.items()
            },
            "trades": [trade.to_dict() for trade in response.trades],
            "equity_curve": [point.to_dict() for point in response.equity_curve],
        }, indent=2, default=str))
        return

    display_swing_backtest(response, show_trades=show_trades)


# ─── size command ─────────────────────────────────────────────────────────────

def size(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Total capital in IDR (default: from config/user.yaml)", min=1),
    ] = None,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade"),
    ] = APP_CFG.swing.risk_pct,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance"),
    ] = APP_CFG.swing.atr_mult,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target"),
    ] = APP_CFG.swing.rr,
    atr_period: Annotated[
        int,
        typer.Option("--atr-period", help="ATR period (default: 14)", min=2),
    ] = 14,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    ATR-based position sizing calculator for IDX swing trades.

    Computes stop price (ATR × multiplier, default 1.5) below entry, target
    at reward:risk ratio (default 2×), and exact lot count from fixed-fractional
    capital risk.

    Examples:
        saham trade size BBRI --capital 10000000
        saham trade size BBRI --capital 10000000 --risk-pct 2 --entry 4825
        saham trade size BBRI --capital 50000000 --risk-pct 1 --rr 2.5
        saham trade size BBRI --capital 10000000 --atr-mult 2.0
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    today = date.today()

    if capital is None:
        _cfg = get_swing_default("capital")
        if _cfg is not None:
            capital = int(_cfg)
    if capital is None:
        typer.echo(
            "Error: --capital is required. Pass it as a flag or set swing.capital in config/user.yaml.",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    registry = create_indicator_registry()

    candles = market_repo.get_candles(ticker_upper)
    if not candles:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham fetch market {ticker_upper} --days 365",
            err=True,
        )
        raise typer.Exit(1)

    latest_close = candles[-1].close

    # Compute ATR
    atr_value: Decimal | None = None
    try:
        atr_values = registry.compute("ATR", candles, atr_period)
        if atr_values:
            atr_value = atr_values[-1][1]  # registry returns (date, value) tuples
    except Exception as e:
        typer.echo(f"Error computing ATR: {e}", err=True)
        raise typer.Exit(1)

    if not atr_value or atr_value <= 0:
        typer.echo(
            f"Cannot compute ATR({atr_period}) for {ticker_upper} — insufficient data.", err=True
        )
        typer.echo(f"Tip: Run: saham fetch market {ticker_upper} --days 90", err=True)
        raise typer.Exit(1)

    entry_dec = Decimal(str(entry_price)) if entry_price else latest_close

    try:
        result = compute_position_size(
            entry=entry_dec,
            atr=atr_value,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            atr_multiplier=Decimal(str(atr_mult)),
            reward_risk=Decimal(str(rr)),
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        out = {
            "ticker": ticker_upper,
            "date": str(today),
            "entry": float(result.entry_price),
            "atr": float(result.atr),
            "atr_period": atr_period,
            "atr_multiplier": float(result.atr_multiplier),
            "stop_price": float(result.stop_price),
            "stop_distance": float(result.stop_distance),
            "stop_pct": float(result.stop_pct),
            "target_price": float(result.target_price),
            "target_pct": float(result.target_pct),
            "reward_risk_ratio": float(result.reward_risk_ratio),
            "capital": float(result.capital),
            "risk_pct": risk_pct,
            "risk_amount": float(result.risk_amount),
            "reward_amount": float(result.reward_amount),
            "lots": result.lots,
            "shares": result.shares,
            "position_cost": float(result.position_cost),
            "capital_used_pct": float(result.capital_used_pct),
        }
        typer.echo(json.dumps(out, indent=2))
        return

    from src.adapters.cli.trade_swing_size_display import display_position_size

    display_position_size(
        ticker=ticker_upper,
        today=today,
        capital=capital,
        risk_pct=risk_pct,
        entry_price=entry_price,
        entry_dec=entry_dec,
        atr_value=atr_value,
        atr_period=atr_period,
        result=result,
    )
