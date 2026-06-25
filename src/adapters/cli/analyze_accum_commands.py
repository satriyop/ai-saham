"""
CLI implementation for saham analyze accum-audit command.

Public command registration lives in lifecycle routers:
  saham analyze accum-audit

Layer: Adapter
"""

import csv
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import UniverseNotFoundError, resolve_tickers
from src.application.use_case.accumulation_audit_use_case import (
    AccumulationAuditRequest,
    AccumulationAuditResponse,
    AccumulationAuditUseCase,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)

AUDIT_SETUPS = {
    "foreign-bounce": {
        "universe": "idx80",
        "window": 7,
        "min_score": 70.0,
        "min_net_buy_days": 2,
        "min_vwap_disc": 3.0,
        "trend": "SIDE",
        "min_flow_pct": 5.0,
        "require_rsi": True,
        "max_rsi": 60.0,
        "simulate_exits": True,
        "take_profits": "4,5,6",
        "stop_losses": "3,5,7",
        "max_holds": "3,5,7,10",
    },
    "coiled-spring": {
        "universe": "idx80",
        "window": 7,
        "min_score": 60.0,
        "min_net_buy_days": 2,
        "min_flow_pct": 3.0,
        "require_rsi": True,
        "max_rsi": 65.0,
        "max_bb_width_pctile": 0.20,
        "simulate_exits": True,
        "take_profits": "4,5,6",
        "stop_losses": "3,5,7",
        "max_holds": "5,7,10,15",
    },
    "smart-money-confirmed": {
        "universe": "idx80",
        "window": 7,
        "min_score": 60.0,
        "min_net_buy_days": 2,
        "broker_quality": "smart+",
        "simulate_exits": True,
        "take_profits": "4,5,6",
        "stop_losses": "3,5,7",
        "max_holds": "3,5,7,10",
    },
    "pullback-continuation": {
        "universe": "idx80",
        "window": 7,
        "min_score": 55.0,
        "min_net_buy_days": 2,
        "min_vwap_disc": -2.0,
        "trend": "UP",
        "min_flow_pct": 2.0,
        "require_rsi": True,
        "min_rsi": 40.0,
        "max_rsi": 65.0,
        "simulate_exits": True,
        "take_profits": "5,8,10",
        "stop_losses": "4,5,7",
        "max_holds": "5,10,15",
    },
}

_AUDIT_SETUP_HELP = ", ".join(AUDIT_SETUPS)


def _display_audit_summary(response: AccumulationAuditResponse, top_groups: int) -> None:
    from src.adapters.cli.analyze_accum_display import display_audit_summary
    display_audit_summary(response=response, top_groups=top_groups)


def _write_audit_csv(response: AccumulationAuditResponse, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.to_dict() for r in response.records]
    fieldnames = list(rows[0].keys()) if rows else [
        "signal_date", "ticker", "score", "streak", "net_buy_ratio",
        "total_net_value", "flow_pct", "vwap_disc_pct", "rsi", "bb_pctile",
        "trend", "broker_quality", "current_price", "return_5d_pct", "return_10d_pct",
        "return_20d_pct", "max_upside_pct", "max_drawdown_pct",
    ]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _parse_float_grid(value: str, option_name: str) -> tuple[float, ...]:
    try:
        parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise typer.BadParameter(f"{option_name} must be comma-separated numbers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise typer.BadParameter(f"{option_name} must contain positive numbers")
    return parsed


def _parse_int_grid(value: str, option_name: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise typer.BadParameter(f"{option_name} must be comma-separated integers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise typer.BadParameter(f"{option_name} must contain positive integers")
    return parsed


def accumulation_audit(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
    ] = None,
    setup: Annotated[
        Optional[str],
        typer.Option("--setup", help=f"Audit setup: {_AUDIT_SETUP_HELP}"),
    ] = None,
    start: Annotated[
        str,
        typer.Option("--start", help="Audit start date, YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Audit end date, YYYY-MM-DD (default: today)"),
    ] = None,
    window: Annotated[
        Optional[int],
        typer.Option("--window", "-w", help="Accumulation window in broker sessions", min=3),
    ] = None,
    min_score: Annotated[
        Optional[float],
        typer.Option("--min-score", help="Minimum composite score to audit", min=0),
    ] = None,
    min_net_buy_days: Annotated[
        Optional[int],
        typer.Option("--min-net-buy-days", help="Minimum foreign net-buy days", min=1),
    ] = None,
    min_vwap_disc: Annotated[
        Optional[float],
        typer.Option(
            "--min-vwap-disc",
            help="Require VWAP discount at least this percent",
        ),
    ] = None,
    trend: Annotated[
        Optional[str],
        typer.Option("--trend", help="Require trend bucket: UP, SIDE, or DOWN"),
    ] = None,
    min_flow_pct: Annotated[
        Optional[float],
        typer.Option("--min-flow-pct", help="Require average foreign flow percent"),
    ] = None,
    require_rsi: Annotated[
        bool,
        typer.Option("--require-rsi", help="Exclude signals with missing RSI"),
    ] = False,
    max_rsi: Annotated[
        Optional[float],
        typer.Option("--max-rsi", help="Require RSI at or below this value"),
    ] = None,
    min_rsi: Annotated[
        Optional[float],
        typer.Option("--min-rsi", help="Require RSI at or above this value"),
    ] = None,
    max_bb_width_pctile: Annotated[
        Optional[float],
        typer.Option("--max-bb-width-pctile", help="Require BB width percentile at or below this value"),
    ] = None,
    broker_quality: Annotated[
        Optional[str],
        typer.Option("--broker-quality", help="Require broker-quality bucket, e.g. smart+"),
    ] = None,
    simulate_exits: Annotated[
        Optional[bool],
        typer.Option("--simulate-exits", help="Run TP/SL/max-hold exit grid"),
    ] = None,
    take_profits: Annotated[
        Optional[str],
        typer.Option("--take-profits", help="Comma-separated take-profit percentages"),
    ] = None,
    stop_losses: Annotated[
        Optional[str],
        typer.Option("--stop-losses", help="Comma-separated stop-loss percentages"),
    ] = None,
    max_holds: Annotated[
        Optional[str],
        typer.Option("--max-holds", help="Comma-separated max holding days"),
    ] = None,
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Forward horizon for max up/down metrics", min=5),
    ] = 20,
    output_path: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Write raw audit records to CSV"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    top_groups: Annotated[
        int,
        typer.Option("--top-groups", help="Number of grouped summary rows to print", min=1),
    ] = 80,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Replay accumulation signals historically and measure forward returns.

    This command is deterministic and offline. It uses cached local candles and
    broker summaries only; run `saham fetch market --universe <name>` first.
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    setup_name = setup.lower() if setup else None
    setup_values = {}
    if setup_name is not None:
        if setup_name not in AUDIT_SETUPS:
            typer.echo(
                f"Error: unknown setup '{setup}'. "
                f"Available setups: {', '.join(AUDIT_SETUPS)}",
                err=True,
            )
            raise typer.Exit(1)
        setup_values = AUDIT_SETUPS[setup_name]

    universe = universe or setup_values.get("universe")
    window = window if window is not None else int(setup_values.get("window", 7))
    min_score = (
        min_score if min_score is not None
        else float(setup_values.get("min_score", 40.0))
    )
    min_net_buy_days = (
        min_net_buy_days if min_net_buy_days is not None
        else int(setup_values.get("min_net_buy_days", 2))
    )
    min_vwap_disc = (
        min_vwap_disc if min_vwap_disc is not None
        else setup_values.get("min_vwap_disc")
    )
    trend = trend or setup_values.get("trend")
    min_flow_pct = (
        min_flow_pct if min_flow_pct is not None
        else setup_values.get("min_flow_pct")
    )
    require_rsi = require_rsi or bool(setup_values.get("require_rsi", False))
    max_rsi = max_rsi if max_rsi is not None else setup_values.get("max_rsi")
    min_rsi = min_rsi if min_rsi is not None else setup_values.get("min_rsi")
    max_bb_width_pctile = (
        max_bb_width_pctile if max_bb_width_pctile is not None
        else setup_values.get("max_bb_width_pctile")
    )
    broker_quality = broker_quality or setup_values.get("broker_quality")
    simulate_exits = (
        simulate_exits if simulate_exits is not None
        else bool(setup_values.get("simulate_exits", False))
    )
    take_profits = take_profits or str(setup_values.get("take_profits", "4,5,6"))
    stop_losses = stop_losses or str(setup_values.get("stop_losses", "3,5,7"))
    max_holds = max_holds or str(setup_values.get("max_holds", "3,5,7,10"))

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

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
            "No tickers to audit. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    trend_filter = trend.upper() if trend else None
    if trend_filter is not None and trend_filter not in {"UP", "SIDE", "DOWN"}:
        typer.echo("Error: --trend must be one of: UP, SIDE, DOWN", err=True)
        raise typer.Exit(1)

    filter_parts = []
    if min_vwap_disc is not None:
        filter_parts.append(f"VWAP>={min_vwap_disc:g}%")
    if trend_filter is not None:
        filter_parts.append(f"trend={trend_filter}")
    if min_flow_pct is not None:
        filter_parts.append(f"flow>={min_flow_pct:g}%")
    if require_rsi:
        filter_parts.append("RSI present")
    if max_rsi is not None:
        filter_parts.append(f"RSI<={max_rsi:g}")
    if min_rsi is not None:
        filter_parts.append(f"RSI>={min_rsi:g}")
    if max_bb_width_pctile is not None:
        filter_parts.append(f"BBpct<={max_bb_width_pctile:g}")
    if broker_quality is not None:
        filter_parts.append(f"broker={broker_quality}")
    if simulate_exits:
        filter_parts.append("exit simulation")
    filter_label = f" | filters: {', '.join(filter_parts)}" if filter_parts else ""

    try:
        take_profit_grid = _parse_float_grid(take_profits, "--take-profits")
        stop_loss_grid = _parse_float_grid(stop_losses, "--stop-losses")
        max_hold_grid = _parse_int_grid(max_holds, "--max-holds")
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format != "json":
        typer.echo(
            f"Auditing {len(ticker_list)} tickers | {start_date} to {end_date} | "
            f"{window} sessions | min score {min_score:g}{filter_label}..."
        )

    use_case = AccumulationAuditUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            window_days=window,
            min_net_buy_days=min_net_buy_days,
            min_score=min_score,
            horizon_days=horizon,
            min_vwap_disc_pct=min_vwap_disc,
            trend=trend_filter,
            min_flow_pct=min_flow_pct,
            require_rsi=require_rsi,
            min_rsi=min_rsi,
            max_rsi=max_rsi,
            max_bb_width_pctile=max_bb_width_pctile,
            broker_quality=broker_quality,
            simulate_exits=simulate_exits,
            take_profit_pcts=take_profit_grid,
            stop_loss_pcts=stop_loss_grid,
            max_hold_days=max_hold_grid,
        )
    )

    if output_path is not None:
        _write_audit_csv(response, output_path)
        typer.echo(f"Wrote {response.total_records} audit records to {output_path}")

    if output_format == "json":
        typer.echo(json.dumps({
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "window_days": response.window_days,
            "total_replay_dates": response.total_replay_dates,
            "total_tickers": response.total_tickers,
            "total_records": response.total_records,
            "skipped_no_forward_data": response.skipped_no_forward_data,
            "warnings": response.warnings,
            "group_stats": [s.to_dict() for s in response.group_stats],
            "exit_simulations": [s.to_dict() for s in response.exit_simulations],
        }, indent=2, default=str))
        return

    _display_audit_summary(response, top_groups=top_groups)
