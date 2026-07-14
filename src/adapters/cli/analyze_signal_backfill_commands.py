"""
CLI commands for SignalEngine historical observations backfilling.

Layer: Adapter
"""

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.services.universe_loader import UniverseNotFoundError, resolve_tickers
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsRequest,
    BackfillSignalObservationsResponse,
    BackfillSignalObservationsUseCase,
)
from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateSignalForwardLabelsUseCase,
)
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.config.swing_config import load_swing_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)


def signal_backfill_observations(
    universe: Annotated[
        str,
        typer.Option("--universe", "-u", help="Universe name, e.g. lq45"),
    ],
    start: Annotated[str, typer.Option("--start", help="Start date YYYY-MM-DD")],
    end: Annotated[str, typer.Option("--end", help="End date YYYY-MM-DD")],
    horizon: Annotated[
        str,
        typer.Option("--horizon", help="TACTICAL_3D, SWING_10D, or ACCUM_20D"),
    ] = SignalLabelHorizon.SWING_10D.value,
    generate_labels: Annotated[
        bool,
        typer.Option("--generate-labels", help="Generate labels for eligible saved dates"),
    ] = False,
    fmt: Annotated[str, typer.Option("--format", help="Output format: table or json")] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Backfill historical candidate observations using local data only."""
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        typer.echo("[error] Invalid date; expected YYYY-MM-DD for --start/--end", err=True)
        raise typer.Exit(1)
    if end_date < start_date:
        typer.echo("[error] --end must be on or after --start", err=True)
        raise typer.Exit(1)
    try:
        label_horizon = SignalLabelHorizon(horizon.upper())
    except ValueError:
        typer.echo(f"[error] Invalid horizon: {horizon}", err=True)
        raise typer.Exit(1)
    try:
        tickers = resolve_tickers(
            universe=universe,
            explicit=[],
            db_path=resolved_db,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(resolved_db),
        )
    except (UniverseNotFoundError, FileNotFoundError) as exc:
        typer.echo(f"[error] {exc}", err=True)
        raise typer.Exit(1)
    if not tickers:
        typer.echo(f"[error] Universe {universe!r} resolved to no tickers.", err=True)
        raise typer.Exit(1)

    observations_repo = SQLiteCandidateObservationsRepository(resolved_db)
    market_repo = SQLiteMarketRepository(resolved_db)
    labels_repo = SQLiteSignalForwardLabelsRepository(resolved_db)
    accumulation_config = load_accumulation_screener_config()
    swing_config = load_swing_config()
    workflow = create_accumulation_screen_workflow(
        db_path=resolved_db,
        screener_config=accumulation_config,
        swing_config=swing_config,
    )
    screen_request_builder = BuildSignalObservationScreenRequest.from_configs(
        swing_config=swing_config,
        accumulation_screener_config=accumulation_config,
        min_net_buy_days=1,
        disable_score_filters=True,
    )
    label_use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    )

    def _evaluate_market_context_for_backfill(*, as_of_date: date) -> MarketContext:
        return evaluate_market_context(
            db_path=resolved_db,
            as_of_date=as_of_date,
            universe=universe,
        )

    response = BackfillSignalObservationsUseCase(
        accumulation_screen_use_case=workflow.use_case,
        screen_request_builder=screen_request_builder,
        market_data_repository=market_repo,
        candidate_observations_repository=observations_repo,
        label_generation_use_case=label_use_case,
        evaluate_market_context=_evaluate_market_context_for_backfill,
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=tuple(tickers),
            start_date=start_date,
            end_date=end_date,
            horizon=label_horizon,
            generate_labels=generate_labels,
        )
    )

    if fmt == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2))
        return
    _display_backfill_response(response)


def _display_backfill_response(response: BackfillSignalObservationsResponse) -> None:
    typer.echo("\nSignal Observation Backfill")
    typer.echo("═" * 72)
    typer.echo(f"Requested trading dates: {response.requested_date_count}")
    typer.echo(f"Processed dates: {response.processed_date_count}")
    typer.echo(f"Skipped entries: {response.skipped_date_count}")
    typer.echo(f"Saved observation rows: {response.saved_observation_count}")
    typer.echo(f"Generated labels: {response.generated_label_count}")
    typer.echo(f"Unavailable labels: {response.unavailable_label_count}")
    if response.processed_dates:
        typer.echo("")
        typer.echo("Processed dates:")
        for processed_date in response.processed_dates:
            typer.echo(f"  - {processed_date.isoformat()}")
    if response.skipped_dates:
        typer.echo("")
        typer.echo("Skipped:")
        for skipped in response.skipped_dates:
            typer.echo(f"  - {skipped.date.isoformat()}: {skipped.reason}")
    if response.notes:
        typer.echo("")
        typer.echo("Notes:")
        for note in response.notes:
            typer.echo(f"  - {note}")
