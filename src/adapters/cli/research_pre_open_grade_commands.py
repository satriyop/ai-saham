"""
CLI: saham research pre-open grade

Computes deterministic accuracy report from saved observations + track data
(ADR-048). Fail closed without research pre-open capture.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.research_pre_open_paths import (
    opening_day_dir,
    parse_session_date,
)
from src.infrastructure.config.app_config import load_app_config


def grade(
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """
    Compute deterministic accuracy report from today's decisions + track data.

    Requires saved DB observations from research pre-open capture and at least
    one track_*.json for the date.

    Examples:
        saham research pre-open grade
        saham research pre-open grade --date 2026-06-17
    """
    run_date = parse_session_date(date_str)
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    try:
        from src.application.use_case.opening_grade_use_case import compute_grade
        from src.infrastructure.config.pre_open_grade_config_loader import (
            load_pre_open_grade_config_snapshot,
        )
        from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
            SQLiteCandidateObservationsRepository,
        )
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    if not resolved_db.exists():
        typer.echo(
            f"Error: observations database not found at {resolved_db}. "
            "Run `saham research pre-open capture` first.",
            err=True,
        )
        raise typer.Exit(1)
    try:
        observations_repo = SQLiteCandidateObservationsRepository(resolved_db)
    except Exception as e:
        typer.echo(f"Error: could not open observations DB ({e})", err=True)
        raise typer.Exit(1)

    try:
        config_snapshot = load_pre_open_grade_config_snapshot()
        result = compute_grade(
            run_date,
            config_snapshot=config_snapshot,
            observations_repository=observations_repo,
        )
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    out_dir = opening_day_dir(run_date)
    typer.echo(f"Grade saved → {out_dir}/grade.json + grade.md")
    typer.echo(f"  Decision source:        {result.get('decision_source', 'n/a')}")
    typer.echo("")
    typer.echo(f"  Entry range hit rate:   {_pct(result.get('entry_range_hit_rate'))}")
    typer.echo(f"  Trend accuracy T+5m:    {_pct(result.get('trend_accuracy_T5'))}")
    typer.echo(f"  Trend accuracy T+30m:   {_pct(result.get('trend_accuracy_T30'))}")
    typer.echo(f"  Clean trade rate:       {_pct(result.get('clean_trade_rate'))}")

    # Champion slices
    bands = result.get("by_signal_band") or {}
    if any((bands.get(b) or {}).get("count", 0) for b in ("strong", "moderate", "weak")):
        typer.echo("")
        typer.echo("  By signal band (champion):")
        for band in ("strong", "moderate", "weak"):
            v = bands.get(band) or {}
            if v.get("count", 0) > 0:
                typer.echo(
                    f"    {band:8s}  n={v['count']}  "
                    f"entry_hit={_pct(v.get('entry_range_hit_rate'))}  "
                    f"clean={_pct(v.get('clean_trade_rate'))}"
                )

    actions = result.get("by_trade_setup_action") or {}
    if any((actions.get(a) or {}).get("count", 0) for a in actions):
        typer.echo("")
        typer.echo("  By TradeSetup action:")
        for action, v in actions.items():
            if action.startswith("_") or not v.get("count", 0):
                continue
            typer.echo(
                f"    {action:20s}  n={v['count']}  "
                f"entry_hit={_pct(v.get('entry_range_hit_rate'))}  "
                f"clean={_pct(v.get('clean_trade_rate'))}"
            )

    # Legacy secondary
    legacy_shown = False
    for opening_setup in ("PRIME", "WATCH", "SKIP"):
        v = result.get("by_opening_setup", {}).get(opening_setup, {})
        if v.get("count", 0) > 0:
            if not legacy_shown:
                typer.echo("")
                typer.echo("  By opening_setup (legacy secondary):")
                legacy_shown = True
            typer.echo(
                f"    {opening_setup:5s}  n={v['count']}  "
                f"entry_hit={_pct(v.get('entry_range_hit_rate'))}  "
                f"clean={_pct(v.get('clean_trade_rate'))}"
            )

    broker_tickers = [
        t
        for t in result.get("per_ticker", [])
        if t.get("institutional_absorption_rate") is not None
    ]
    if broker_tickers:
        typer.echo("")
        typer.echo("  Broker Confirmation (institutional absorption):")
        for t in broker_tickers:
            side = t.get("broker_dominant_side", "?")
            abs_rate = t.get("institutional_absorption_rate")
            typer.echo(f"    {t['ticker']:8s}  {side:7s}  abs={_pct(abs_rate)}")

    ob_tickers = [t for t in result.get("per_ticker", []) if t.get("bid_pressure_T0") is not None]
    if ob_tickers:
        typer.echo("")
        typer.echo("  Order Book Depth (bid pressure ratio + live F.Net):")
        for t in ob_tickers:
            bp_t0 = t.get("bid_pressure_T0")
            bp_t5 = t.get("bid_pressure_T5")
            momentum = t.get("bid_momentum")
            fnet = t.get("fnet_latest")
            fnet_str = f"{fnet / 1e9:+.1f}B" if fnet is not None else "?"
            momentum_str = f"{momentum:+.3f}" if momentum is not None else "?"
            bp_t5_str = _pct(bp_t5) if bp_t5 is not None else "?"
            typer.echo(
                f"    {t['ticker']:8s}  bp_T0={_pct(bp_t0)}  bp_T5={bp_t5_str}"
                f"  Δ={momentum_str}  F.Net={fnet_str}"
            )


def _pct(v) -> str:
    return f"{v * 100:.1f}%" if v is not None else "N/A"
