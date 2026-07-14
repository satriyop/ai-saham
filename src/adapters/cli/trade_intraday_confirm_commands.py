"""CLI commands for active intraday trading workflows. Layer: Adapter."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from src.adapters.cli.trade_intraday_confirm_factory import (
    IntradayAutoConfirmSetupError,
    create_run_intraday_confirmation_workflow,
)
from src.adapters.cli.trade_intraday_confirmation_journal_actions import (
    run_confirm_outcome,
    run_confirm_review,
)
from src.adapters.cli.trade_intraday_display import (
    display_confirmations,
    format_opening_observation_status,
    format_ticker_preview,
)
from src.application.dto.intraday_confirmation_workflow import (
    RunIntradayConfirmationWorkflowRequest,
)
from src.application.use_case.log_intraday_confirmation_use_case import (
    LogIntradayConfirmationRequest,
    LogIntradayConfirmationUseCase,
)
from src.application.use_case.run_intraday_confirmation_workflow_use_case import (
    EVENT_AUTO_RESOLUTION_NEEDED,
    EVENT_MANUAL_PRICES,
    EVENT_OBSERVATION,
    EVENT_REGIME_WARNING,
    EVENT_RESOLUTION_SUMMARY,
    EVENT_STARTED,
    EVENT_TRACK_PRICES,
    IntradayAutoResolutionUnavailable,
    IntradayTrackFileParseError,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.intraday_confirmation_csv import (
    IntradayConfirmationCsvStore,
)
from src.infrastructure.persistence.trade_journal_jsonl_writer import (
    TradeJournalJsonlWriter,
)


def _make_confirm_progress_printer(sidecar_path: Path):
    def _on_event(event: str, payload: dict[str, Any]) -> None:
        if event == EVENT_STARTED:
            typer.echo(
                f"Confirming {len(payload['tickers'])} pre-open candidate(s) "
                f"from {sidecar_path} for {payload['screened_at']}."
            )
        elif event == EVENT_MANUAL_PRICES:
            typer.echo(f"Manual opening prices supplied: {payload['count']}")
        elif event == EVENT_TRACK_PRICES:
            typer.echo(f"Track file opening prices resolved: {payload['count']}")
        elif event == EVENT_AUTO_RESOLUTION_NEEDED:
            typer.echo(
                "Resolving missing opening prices from Stockbit: "
                f"{format_ticker_preview(payload['missing'])}"
            )
            typer.echo(
                "Tip: pass --opening-json or --track-file "
                "to skip browser-backed auto resolution."
            )
        elif event == EVENT_OBSERVATION:
            typer.echo(
                format_opening_observation_status(
                    payload["index"], payload["total"], payload["observation"]
                )
            )
        elif event == EVENT_RESOLUTION_SUMMARY:
            typer.echo(
                f"Opening prices resolved: {payload['resolved_count']}/{payload['total']}"
            )
            if payload["unresolved"]:
                typer.echo("Unresolved opening prices:")
                for obs in payload["unresolved"]:
                    typer.echo(f"  - {obs.ticker}: {obs.reason or 'no usable opening price'}")
        elif event == EVENT_REGIME_WARNING:
            typer.echo(payload["warning"], err=True)

    return _on_event


def confirm_open(
    opening_json: Annotated[
        Optional[str], typer.Option("--opening-json", help="Manual prices JSON")
    ] = None,
    track_file: Annotated[
        Optional[Path], typer.Option("--track-file", help="Track file for offline prices")
    ] = None,
    session: Annotated[
        Optional[Path], typer.Option("--session", help="Pre-open sidecar JSON path")
    ] = None,
    output: Annotated[
        Optional[Path], typer.Option("--output", help="Confirmation output path")
    ] = None,
    max_stop: Annotated[
        float, typer.Option("--max-stop", help="Max stop decimal, 0.07=7%")
    ] = 0.07,
    headless: Annotated[
        bool, typer.Option("--headless/--no-headless", help="Headless browser for auto-confirm")
    ] = True,
) -> None:
    cfg = load_app_config()
    sidecar_path = session or Path(cfg.storage.intraday_sidecar)
    output_path = output or Path(cfg.storage.intraday_confirmation)
    if not sidecar_path.exists():
        typer.echo(
            f"No session sidecar at '{sidecar_path}'.\n"
            "Run `saham screen pre-open` first.", err=True,
        )
        raise typer.Exit(1)

    manual_prices: dict[str, Decimal] = {}
    if opening_json:
        try:
            raw_opening = json.loads(opening_json)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid --opening-json: {e}", err=True)
            raise typer.Exit(1)
        if not isinstance(raw_opening, dict):
            typer.echo("Error: --opening-json must be a JSON object.", err=True)
            raise typer.Exit(1)
        try:
            manual_prices = {
                str(t.upper()): Decimal(str(p))
                for t, p in raw_opening.items() if p is not None
            }
        except Exception as e:
            typer.echo(f"Error: opening prices must be numeric: {e}", err=True)
            raise typer.Exit(1)

    if max_stop <= 0:
        typer.echo("Error: --max-stop must be positive.", err=True)
        raise typer.Exit(1)

    live_auto_resolution_enabled = track_file is None

    workflow = create_run_intraday_confirmation_workflow(
        live_auto_resolution_enabled=live_auto_resolution_enabled,
        on_event=_make_confirm_progress_printer(sidecar_path),
    )

    try:
        result = workflow.execute(
            RunIntradayConfirmationWorkflowRequest(
                sidecar_path=sidecar_path,
                output_path=output_path,
                max_stop_pct=Decimal(str(max_stop)),
                manual_prices=manual_prices,
                track_file=track_file,
                live_auto_resolution_enabled=live_auto_resolution_enabled,
            )
        )
    except IntradayAutoResolutionUnavailable as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    except IntradayAutoConfirmSetupError as e:
        typer.echo(
            f"Auto confirm setup failed: {e}. "
            "Pass --opening-json or --track-file to confirm manually.", err=True,
        )
        raise typer.Exit(1)
    except IntradayTrackFileParseError as e:
        typer.echo(f"Error parsing track file '{track_file}': {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        missing_path = e.args[0] if e.args else None
        if track_file is not None and missing_path == track_file:
            typer.echo(f"Error: Track file not found at '{track_file}'", err=True)
        else:
            typer.echo(
                f"No session sidecar at '{sidecar_path}'.\n"
                "Run `saham screen pre-open` first.", err=True,
            )
        raise typer.Exit(1)

    # Regime warnings are echoed live via the on_event callback (EVENT_REGIME_WARNING)
    # to preserve the original print ordering relative to resolution output.
    display_confirmations(
        result.confirmations, result.confirmed_date,
        result.max_stop_pct, extras=result.extras,
    )


def _confirm_log_impl(confirmation_path: Path, journal_path: Path) -> None:
    confirm_log(confirmation=confirmation_path, journal=journal_path)


def confirm_log(
    confirmation: Annotated[
        Optional[Path], typer.Option("--confirmation", help="Confirmation sidecar path")
    ] = None,
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Intraday CSV journal")
    ] = None,
) -> None:
    cfg = load_app_config()
    confirmation_path = confirmation or Path(cfg.storage.intraday_confirmation)
    journal_path = journal or Path(cfg.storage.intraday_confirmation_journal)
    csv_store = IntradayConfirmationCsvStore(journal_path)
    jsonl_store = TradeJournalJsonlWriter(confirmation_path.parent / "trades.jsonl")
    use_case = LogIntradayConfirmationUseCase(
        confirmation_store=csv_store, trade_journal_store=jsonl_store,
    )
    try:
        response = use_case.execute(
            LogIntradayConfirmationRequest(
                confirmation_path=confirmation_path, journal_path=journal_path,
            )
        )
    except FileNotFoundError:
        typer.echo(
            f"No confirmation sidecar at '{confirmation_path}'.\n"
            "Run `saham trade confirm` first.", err=True,
        )
        raise typer.Exit(1)
    except json.JSONDecodeError:
        typer.echo(
            f"Error: invalid confirmation sidecar at '{confirmation_path}'.", err=True,
        )
        raise typer.Exit(1)
    if response.duplicate:
        typer.echo(
            f"Already logged for {response.confirmed_at} — "
            f"no new rows added ({response.journal_path})"
        )
    else:
        typer.echo(
            f"Logged {response.logged_count} confirmation(s) "
            f"for {response.confirmed_at} → {response.journal_path}"
        )


def confirm_review(
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Intraday CSV journal")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    cfg = load_app_config()
    run_confirm_review(
        journal_path=journal or Path(cfg.storage.intraday_confirmation_journal),
        db_path=db_path or Path(cfg.storage.db_path),
    )


def confirm_outcome(
    ticker: Annotated[str, typer.Argument(help="Ticker to update")],
    entry: Annotated[float, typer.Option("--entry", help="Actual entry price", min=0.0001)],
    exit_price: Annotated[float, typer.Option("--exit", help="Actual exit price", min=0.0001)],
    result: Annotated[
        str, typer.Option("--result", help="Outcome: target/stop/manual/breakeven")
    ] = "manual",
    confirmed_date: Annotated[
        Optional[str], typer.Option("--date", help="Date YYYY-MM-DD")
    ] = None,
    notes: Annotated[
        Optional[str], typer.Option("--notes", help="Execution notes")
    ] = None,
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Intraday CSV journal")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    cfg = load_app_config()
    run_confirm_outcome(
        ticker=ticker,
        entry=entry,
        exit_price=exit_price,
        result=result,
        confirmed_date=confirmed_date,
        notes=notes,
        journal_path=journal or Path(cfg.storage.intraday_confirmation_journal),
        db_path=db_path or Path(cfg.storage.db_path),
    )
