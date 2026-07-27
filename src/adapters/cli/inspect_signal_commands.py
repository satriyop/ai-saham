"""
CLI: provisional read-only canonical signal inspection (DQ-007).

Permanent hierarchy ``saham inspect signal`` is owned by CLI-002.
This provisional command wires the verified use case only.

Layer: Adapter (parse, wire, format, map errors). No PIT/score policy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.effective_session_display import (
    format_effective_session_line,
    parse_as_of_option,
)
from src.adapters.composition.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow_bundle,
)
from src.application.dto.inspect_canonical_signal import (
    InspectCanonicalSignalRequest,
    InspectCanonicalSignalStatus,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.use_case.inspect_canonical_signal_use_case import (
    InspectCanonicalSignalUseCase,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.swing_config_loader import load_swing_config
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def signal_inspect(
    ticker: Annotated[str, typer.Argument(help="IDX ticker (e.g. BBCA)")],
    as_of_date: Annotated[
        Optional[str],
        typer.Option(
            "--as-of",
            help="Point-in-time as-of date YYYY-MM-DD (defaults to today).",
        ),
    ] = None,
    window_days: Annotated[
        int,
        typer.Option("--window-days", help="Accumulation window sessions."),
    ] = 7,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Inspect live canonical SignalEngine scoring for one ticker (read-only).

    Contract: accumulation-flow (same boundary as the accumulation screen).
    Public path: ``saham inspect signal``.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    ticker_u = ticker.upper()

    day = parse_as_of_option(as_of_date)

    try:
        swing_cfg = load_swing_config()
        accum_cfg = load_accumulation_screener_config()
        request_builder = BuildSignalObservationScreenRequest.from_configs(
            swing_config=swing_cfg,
            accumulation_screener_config=accum_cfg,
            min_net_buy_days=max(1, int(window_days)),
            disable_score_filters=True,
        )
        screen_bundle = create_accumulation_screen_workflow_bundle(
            db_path=resolved_db,
            screener_config=accum_cfg,
            swing_config=swing_cfg,
        )
        market_repo = SQLiteMarketRepository(resolved_db)
        response = InspectCanonicalSignalUseCase(
            screen_use_case=screen_bundle.screen_use_case,
            screen_request_builder=request_builder,
            session_resolver=EffectiveMarketSessionResolver(market_repo),
        ).execute(
            InspectCanonicalSignalRequest(
                ticker=ticker_u,
                as_of_date=day,
                window_days=window_days,
            )
        )
    except Exception as exc:
        typer.echo(f"[error] Failed to inspect canonical signal: {exc}", err=True)
        raise typer.Exit(1)

    if fmt == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2))
    else:
        _display(response)

    if response.status is not InspectCanonicalSignalStatus.OK:
        raise typer.Exit(1)


def _display(response) -> None:
    typer.echo(f"\nSignal Inspect · {response.ticker} · {response.contract.value}")
    typer.echo("═" * 78)
    typer.echo(f"Status: {response.status.value}")
    typer.echo(f"As-of: {response.as_of_date.isoformat()}")
    if response.effective_session is not None:
        typer.echo(format_effective_session_line(response.effective_session))
    if response.screen_result is not None:
        typer.echo(f"Screen result: {response.screen_result}")
    if response.assessment is not None:
        a = response.assessment
        typer.echo("")
        typer.echo(
            "Assessment: "
            f"score={a.assessment.score}, "
            f"strength={a.assessment.strength.value}, "
            f"entry_quality={a.assessment.entry_quality.value}, "
            f"signal_authority_coverage={a.signal_authority_coverage}"
        )
        if a.setup_readiness is not None:
            typer.echo(f"Setup readiness: {a.setup_readiness.to_dict()}")
        constraints = a.assessment.decision_constraints
        if constraints is not None:
            typer.echo(f"Decision constraints: {constraints.to_dict()}")
        if a.flow_source_availability is not None:
            typer.echo(
                f"Flow source availability: {a.flow_source_availability.to_dict()}"
            )
        if a.assessment.rationale:
            typer.echo("Rationale:")
            for line in a.assessment.rationale:
                typer.echo(f"  - {line}")
    if response.reasons:
        typer.echo("")
        typer.echo("Reasons:")
        for reason in response.reasons:
            typer.echo(f"  - {reason}")
    if response.notes:
        typer.echo("")
        typer.echo("Notes:")
        for note in response.notes:
            typer.echo(f"  - {note}")
