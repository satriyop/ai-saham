"""
CLI implementation functions for swing position sizing command.

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.position_sizer import compute_position_size
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


def size(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    capital: Annotated[
        Optional[int],
        typer.Option(
            "--capital",
            "-c",
            help="Total capital in IDR (default: from config/user.yaml)",
            min=1,
        ),
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
    ] = APP_CFG.analysis.format,
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
            "Error: --capital is required. Pass it as a flag or set "
            "swing.capital in config/user.yaml.",
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
