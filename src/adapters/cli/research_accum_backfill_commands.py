"""
CLI commands for SignalEngine historical observations backfilling.

Layer: Adapter
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.composition.accumulation_production_policy_bundle import (
    resolve_accumulation_production_policy_bundle,
)
from src.adapters.composition.producer_source_revision import (
    resolve_producer_source_revision,
)
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
from src.application.services.pit_tradable_membership import (
    resolve_pit_tradable_membership,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    load_universe,
)
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsRequest,
    BackfillSignalObservationsResponse,
    BackfillSignalObservationsUseCase,
)
from src.application.use_case.ensure_accumulation_policy_snapshots_use_case import (
    EnsureAccumulationPolicySnapshotsRequest,
    EnsureAccumulationPolicySnapshotsUseCase,
)
from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.config.swing_policy_config_loader import load_swing_policy_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.ihsg_trading_session_calendar_provider import (
    IHSGTradingSessionCalendarProvider,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
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
    "plan_swing",
    "risk_engine",
    "signal_engine",
    "institutional_accumulation",
    "ticker_profile",
    "sector_context",
    "company_quality_context",
    "market_context_engine",
)


def _read_scoring_config_canonical(
    config_paths,
    *,
    pit_tradable_lookback_sessions: int,
) -> str:
    """Read the resolved scoring config file contents into a deterministic
    canonical string.

    The adapter owns file I/O only; it performs NO hashing. Each file is
    rendered as a path-labelled block, blocks are ordered by path so the string
    is deterministic regardless of attribute order, and a NUL delimiter keeps
    file boundaries unambiguous. The application resolver hashes this string.

    ``pit_tradable_lookback_sessions`` (N) is corpus-material and is folded in
    explicitly so changing N forks the lean cohort without hashing all of
    ``default.yaml``.
    """
    rel_paths = sorted({getattr(config_paths, attr) for attr in _SCORING_CONFIG_PATH_ATTRS})
    blocks = []
    for rel_path in rel_paths:
        content = Path(rel_path).read_text(encoding="utf-8")
        blocks.append(f"# path: {rel_path}\n{content}")
    blocks.append(f"# pit_tradable_lookback_sessions\n{int(pit_tradable_lookback_sessions)}")
    return "\n\x00\n".join(blocks)


def run_signal_observation_corpus_write(
    *,
    universe: str,
    start_date: date,
    end_date: date,
    resolved_db: Path,
) -> BackfillSignalObservationsResponse:
    """Compose and run observation corpus write for a date range.

    Shared by ``research accum backfill`` and ``research accum capture``.
    Adapter owns I/O and wiring; ``BackfillSignalObservationsUseCase`` owns policy.

    Membership is point-in-time tradable (candle presence), re-derived per date
    inside the use case. Stamps ``{universe}@pit``.
    """
    cfg = load_app_config()
    pit_window = int(cfg.analysis.pit_tradable_lookback_sessions)
    if pit_window < 1:
        typer.echo(
            f"[error] analysis.pit_tradable_lookback_sessions must be >= 1, got {pit_window}",
            err=True,
        )
        raise typer.Exit(1)

    loader = YamlUniverseConfigLoader()
    named_tickers: list[str] | None
    if universe == "cached":
        # Board-wide pure candle-active — do not intersect with broker cache.
        named_tickers = None
    else:
        try:
            named_tickers = load_universe(universe, loader)
        except (UniverseNotFoundError, FileNotFoundError) as exc:
            typer.echo(f"[error] {exc}", err=True)
            raise typer.Exit(1)
        if not named_tickers:
            typer.echo(f"[error] Universe {universe!r} resolved to no tickers.", err=True)
            raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(resolved_db)

    def membership_resolver(as_of: date) -> tuple[str, ...]:
        return resolve_pit_tradable_membership(
            as_of_date=as_of,
            window_sessions=pit_window,
            market_repository=market_repo,
            named_tickers=named_tickers,
        )

    # Bracket every production-policy config resolve with byte-identical
    # canonical reads.  The application ensure use case rejects a changed
    # generation before snapshots or observations can be written.
    resolved_config_canonical = _read_scoring_config_canonical(
        cfg.config_paths,
        pit_tradable_lookback_sessions=pit_window,
    )

    accumulation_config = load_accumulation_screener_config()
    swing_policy = load_swing_policy_config()

    # Resolve production policies ONCE. The same typed objects are injected into
    # SignalEngine, AssessRiskUseCase, ScoreAccum policy, and snapshot ensure
    # so observations and learning_policy_snapshots share object identity.
    production_policy_bundle = resolve_accumulation_production_policy_bundle(
        accum_score_policy=accumulation_config.accum_score_policy,
    )
    screen_bundle = create_accumulation_screen_workflow_bundle(
        db_path=resolved_db,
        screener_config=accumulation_config,
        swing_policy=swing_policy,
        production_policy_bundle=production_policy_bundle,
    )
    screen_request_builder = BuildSignalObservationScreenRequest.from_configs(
        swing_policy=swing_policy,
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

    # Confirm the typed policies above were resolved while the exact material
    # config generation remained stable.  This second read is validation only;
    # hashing and fail-closed policy remain in the application use case.
    verified_config_canonical = _read_scoring_config_canonical(
        cfg.config_paths,
        pit_tradable_lookback_sessions=pit_window,
    )
    observation_identity = LeanObservationIdentity(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=resolve_lean_semantic_compatibility_id(resolved_config_canonical),
    )

    learning_repo = SQLiteLearningArtifactRepository(resolved_db)
    try:
        EnsureAccumulationPolicySnapshotsUseCase(learning_repo).execute(
            EnsureAccumulationPolicySnapshotsRequest(
                resolved_config_canonical=resolved_config_canonical,
                verified_config_canonical=verified_config_canonical,
                observation_identity=observation_identity,
                accum_score_policy=production_policy_bundle.accum_score_policy,
                signal_engine_config=production_policy_bundle.signal_engine_config,
                structural_gates=production_policy_bundle.structural_gates,
                execution_gates=production_policy_bundle.execution_gates,
                created_at=datetime.now(timezone.utc),
                source_revision=resolve_producer_source_revision(),
            )
        )
    except LearningContractError as exc:
        typer.echo(f"[error] production policy snapshot ensure failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    return BackfillSignalObservationsUseCase(
        record_observations_use_case=screen_bundle.record_observations_use_case,
        screen_request_builder=screen_request_builder,
        market_data_repository=market_repo,
        observation_identity=observation_identity,
        membership_resolver=membership_resolver,
        pit_window_sessions=pit_window,
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
            start_date=start_date,
            end_date=end_date,
            # PIT tradable membership identity. Use case owns survivorship text.
            universe_membership_source=f"{universe}@pit",
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
    """Backfill historical accumulation learning observations from local data.

    Uses point-in-time tradable membership (candle presence over N sessions),
    stamped as ``{universe}@pit``. Not historical index membership.
    """
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
    typer.echo(f"  Universe size (range union): {response.universe_size}")
    typer.echo(f"  Evaluated: {response.evaluated_count}")
    typer.echo(f"  Selected: {response.selected_count}")
    typer.echo(
        f"  Rejected: {response.rejected_count} "
        "(usually 0 by design: capture neutralizes score/structural reject gates)"
    )
    typer.echo(f"  Unavailable: {response.unavailable_count}")
    typer.echo(f"  Universe membership source: {response.universe_membership_source}")
    if response.survivorship_limitation:
        typer.echo(f"  Survivorship limitation: {response.survivorship_limitation}")
    typer.echo(
        f"  Contains screen-rejected control: {response.contains_control_population} "
        f"({response.recall_eligibility})"
    )
    if not response.contains_control_population:
        typer.echo(
            "  Note: not a bug in PIT membership — broker-observable capture is "
            "negative-inclusive by labels, but not a screen-reject census. "
            "Do not claim screener recall/precision until filter-replay is activated."
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
