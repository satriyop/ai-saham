"""
CLI commands for SignalEngine historical observations backfilling.

Layer: Adapter
"""

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.composition.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow_bundle,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
    resolve_lean_semantic_compatibility_id,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
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
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.config.swing_config import load_swing_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.ihsg_trading_session_calendar_provider import (
    IHSGTradingSessionCalendarProvider,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

# Scoring config files whose resolved content is folded into the lean
# semantic_compatibility_id. The full scoring set: any material change to any
# of these forks the learning cohort. Over-forking on a cosmetic edit is safe;
# silent under-forking is the failure mode this hash prevents.
_SCORING_CONFIG_PATH_ATTRS = (
    "accumulation_screener",
    "swing_setups",
    "swing_targets",
    "swing_risk_policy",
    "analyze_swing",
    "signal_engine",
    "institutional_accumulation",
    "ticker_profile",
    "sector_context",
    "company_quality_context",
    "market_context_engine",
)


def _read_scoring_config_canonical(config_paths) -> str:
    """Read the resolved scoring config file contents into a deterministic
    canonical string.

    The adapter owns file I/O only; it performs NO hashing. Each file is
    rendered as a path-labelled block, blocks are ordered by path so the string
    is deterministic regardless of attribute order, and a NUL delimiter keeps
    file boundaries unambiguous. The application resolver hashes this string.
    """
    rel_paths = sorted({getattr(config_paths, attr) for attr in _SCORING_CONFIG_PATH_ATTRS})
    blocks = []
    for rel_path in rel_paths:
        content = Path(rel_path).read_text(encoding="utf-8")
        blocks.append(f"# path: {rel_path}\n{content}")
    return "\n\x00\n".join(blocks)


def run_signal_observation_corpus_write(
    *,
    universe: str,
    start_date: date,
    end_date: date,
    resolved_db: Path,
) -> BackfillSignalObservationsResponse:
    """Compose and run observation corpus write for a date range.

    Shared by ``research signal backfill`` and ``research signal capture``.
    Adapter owns I/O and wiring; ``BackfillSignalObservationsUseCase`` owns policy.
    """
    cfg = load_app_config()
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

    market_repo = SQLiteMarketRepository(resolved_db)
    accumulation_config = load_accumulation_screener_config()
    swing_config = load_swing_config()
    screen_bundle = create_accumulation_screen_workflow_bundle(
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

    def _evaluate_market_context_for_corpus(*, as_of_date: date) -> MarketContext:
        return evaluate_market_context(
            db_path=resolved_db,
            as_of_date=as_of_date,
            universe=universe,
        )

    # Resolve the lean observation identity ONCE. The adapter reads config file
    # contents (I/O) and passes the canonical string to the application
    # resolver, which owns the hashing/policy.
    observation_identity = LeanObservationIdentity(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=resolve_lean_semantic_compatibility_id(
            _read_scoring_config_canonical(cfg.config_paths)
        ),
    )

    return BackfillSignalObservationsUseCase(
        record_observations_use_case=screen_bundle.record_observations_use_case,
        screen_request_builder=screen_request_builder,
        market_data_repository=market_repo,
        observation_identity=observation_identity,
        evaluate_market_context=_evaluate_market_context_for_corpus,
        session_resolver=EffectiveMarketSessionResolver(market_repo),
        evidence_context_builder=SignalEvidenceExecutionContextBuilder(
            trading_session_calendar_loader=lambda start, end: IHSGTradingSessionCalendarProvider(
                market_repo
            ).load(
                coverage_start=start,
                coverage_end=end,
            ),
        ),
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=tuple(tickers),
            start_date=start_date,
            end_date=end_date,
            # Current-universe membership identity. Historical membership is
            # unavailable; the use case turns the `@current` suffix into the
            # survivorship limitation note (adapter passes identity only).
            universe_membership_source=f"{universe}@current",
        )
    )


def signal_backfill_observations(
    universe: Annotated[
        str,
        typer.Option("--universe", "-u", help="Universe name, e.g. lq45"),
    ],
    start: Annotated[str, typer.Option("--start", help="Start date YYYY-MM-DD")],
    end: Annotated[str, typer.Option("--end", help="End date YYYY-MM-DD")],
    fmt: Annotated[str, typer.Option("--format", help="Output format: table or json")] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Backfill historical accumulation learning observations from local data."""
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
    response = run_signal_observation_corpus_write(
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        resolved_db=resolved_db,
    )

    if fmt == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2))
        return
    _display_backfill_response(response, title="Signal Observation Backfill")


def _display_backfill_response(
    response: BackfillSignalObservationsResponse,
    *,
    title: str = "Signal Observation Backfill",
) -> None:
    typer.echo(f"\n{title}")
    typer.echo("═" * 72)
    typer.echo(f"Requested trading dates: {response.requested_date_count}")
    typer.echo(f"Processed dates: {response.processed_date_count}")
    typer.echo(f"Skipped entries: {response.skipped_date_count}")
    typer.echo(f"Saved observation rows: {response.saved_observation_count}")
    typer.echo(f"Generated labels: {response.generated_label_count}")
    typer.echo(f"Unavailable labels: {response.unavailable_label_count}")
    typer.echo("")
    typer.echo("Capture boundary:")
    typer.echo(f"  Universe size: {response.universe_size}")
    typer.echo(f"  Evaluated: {response.evaluated_count}")
    typer.echo(f"  Selected: {response.selected_count}")
    typer.echo(f"  Rejected: {response.rejected_count} (0 by construction; reject gates disabled)")
    typer.echo(f"  Unavailable: {response.unavailable_count}")
    typer.echo(f"  Universe membership source: {response.universe_membership_source}")
    if response.survivorship_limitation:
        typer.echo(f"  Survivorship limitation: {response.survivorship_limitation}")
    typer.echo(
        f"  Contains screen-rejected control: {response.contains_control_population} "
        f"({response.recall_eligibility})"
    )
    if response.ticker_exclusions:
        typer.echo("")
        typer.echo("Ticker exclusions:")
        for exclusion in response.ticker_exclusions:
            typer.echo(f"  - {exclusion.date.isoformat()} {exclusion.ticker}: {exclusion.reason}")
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
