"""
CLI: saham backtest screen accum

Offline historical replay of accumulation discovery filters (+ optional exit grid).
Not corpus evaluate (`research accum evaluate`). Not portfolio sim (`backtest portfolio swing`).

Layer: Adapter
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.backtest_screen_accum_csv_writer import write_accumulation_audit_csv
from src.adapters.cli.backtest_screen_accum_workflow_factory import (
    create_run_accumulation_audit_workflow,
)
from src.adapters.cli.cli_errors import (
    raise_data_unavailable,
    raise_user_error,
)
from src.application.services.universe_loader import UniverseNotFoundError
from src.application.use_case.accumulation_audit_use_case import AccumulationAuditResponse
from src.application.use_case.run_accumulation_audit_workflow_use_case import (
    NoTickersError,
    RunAccumulationAuditWorkflowRequest,
)
from src.infrastructure.config.app_config import load_app_config


def _display_audit_summary(response: AccumulationAuditResponse, top_groups: int) -> None:
    from src.adapters.cli.backtest_screen_accum_display import display_audit_summary

    display_audit_summary(response=response, top_groups=top_groups)


def screen_accum(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"
        ),
    ] = None,
    setup: Annotated[
        Optional[str],
        typer.Option("--setup", help="Audit setup name"),
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
    min_accum_score: Annotated[
        Optional[float],
        typer.Option(
            "--min-foreign-flow-score",
            help="Minimum composite foreign-flow score to audit",
            min=0,
        ),
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
        typer.Option(
            "--max-bb-width-pctile", help="Require BB width percentile at or below this value"
        ),
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
        Optional[int],
        typer.Option("--horizon", help="Forward horizon for max up/down metrics", min=5),
    ] = None,
    output_path: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Write raw audit records to CSV"),
    ] = None,
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
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
    Offline accum-screen filter replay: historical hits + forward/exit stats.

    Not corpus (`research accum evaluate`). Not portfolio book (`backtest portfolio swing`).
    Uses local candles/broker cache only — `saham fetch market --universe <name>` first.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    output_format = output_format or cfg.analysis.format

    workflow = create_run_accumulation_audit_workflow(db_path=resolved_db)
    request = RunAccumulationAuditWorkflowRequest(
        tickers=list(tickers) if tickers else [],
        universe=universe,
        setup=setup,
        start=start,
        end=end,
        window=window,
        min_accum_score=min_accum_score,
        min_net_buy_days=min_net_buy_days,
        min_vwap_disc=min_vwap_disc,
        trend=trend,
        min_flow_pct=min_flow_pct,
        require_rsi=require_rsi,
        max_rsi=max_rsi,
        min_rsi=min_rsi,
        max_bb_width_pctile=max_bb_width_pctile,
        broker_quality=broker_quality,
        simulate_exits=simulate_exits,
        take_profits=take_profits,
        stop_losses=stop_losses,
        max_holds=max_holds,
        horizon=horizon,
    )

    try:
        result = workflow.execute(request)
    except NoTickersError as e:
        raise_user_error(str(e))
    except UniverseNotFoundError as e:
        raise_user_error(str(e), tip="See: saham fetch universe list")
    except FileNotFoundError as e:
        raise_data_unavailable(str(e), tip="Run: saham fetch universe update")
    except ValueError as e:
        raise_user_error(str(e))

    response = result.response

    if output_format != "json":
        typer.echo(
            f"Auditing {result.ticker_count} tickers | "
            f"{result.start_date} to {result.end_date} | "
            f"{result.window} sessions | min foreign-flow score "
            f"{result.min_accum_score:g}{result.filter_label}..."
        )

    if output_path is not None:
        write_accumulation_audit_csv(response, output_path)
        typer.echo(
            f"Wrote {response.total_records} audit records to {output_path}",
            err=output_format == "json",
        )

    if output_format == "json":
        typer.echo(json.dumps(result.to_json_dict(), indent=2, default=str))
        return

    _display_audit_summary(response, top_groups=top_groups)
