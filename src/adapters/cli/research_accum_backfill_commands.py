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
from src.application.services.accumulation_producer_readiness import (
    assess_cohort_fork_warning,
)
from src.application.services.behavioral_cohort_identity import (
    AccumulationCohortIdentity,
    resolve_accumulation_cohort_identity,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
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
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractError,
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
from src.infrastructure.config.swing_policy_config_loader import load_swing_policy_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.ihsg_trading_session_calendar_provider import (
    IHSGTradingSessionCalendarProvider,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    LearningArtifactReadIntegrityError,
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def _echo_cohort_identity(identity: AccumulationCohortIdentity) -> None:
    """Print the authoritative ADR-068 cohort id and the three parts it folds.

    Written to **stderr** on purpose. ``--format json`` stdout is the machine
    contract this command already publishes (the nightly cron calls it with
    ``--format json``), and the per-axis digests are operator attribution aids,
    not a second identity surface for a downstream consumer to key on. stderr
    reaches the operator on both output formats and is captured by the cron log
    redirect.
    """
    typer.echo(
        f"[cohort-identity] compatibility_id:            "
        f"{identity.semantic_compatibility_id.value}",
        err=True,
    )
    typer.echo(
        f"[cohort-identity]   behavioural probe digest:  sha256:{identity.behavioral_probe_digest}",
        err=True,
    )
    typer.echo(
        f"[cohort-identity]   snapshot payload digest:   "
        f"sha256:{identity.policy_snapshot_payload_digest}",
        err=True,
    )
    typer.echo(
        f"[cohort-identity]   payload schema version:    "
        f"{identity.observation_payload_schema_version}",
        err=True,
    )


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

    accumulation_config = load_accumulation_screener_config()
    swing_policy = load_swing_policy_config()

    # Resolve production policies ONCE. The same typed objects are injected into
    # SignalEngine, AssessRiskUseCase, ScoreAccum policy, and snapshot ensure
    # so observations and learning_policy_snapshots share object identity.
    production_policy_bundle = resolve_accumulation_production_policy_bundle(
        accum_score_policy=accumulation_config.accum_score_policy,
        swing_policy=swing_policy,
        accumulation_screener_config=accumulation_config,
    )
    screen_bundle = create_accumulation_screen_workflow_bundle(
        db_path=resolved_db,
        screener_config=accumulation_config,
        swing_policy=swing_policy,
        production_policy_bundle=production_policy_bundle,
    )
    # Capture neutralizes score filters on a derived request only. Snapshot
    # ensure uses production_policy_bundle.hard_filter_policy (pre-neutralization).
    screen_request_builder = BuildSignalObservationScreenRequest.from_configs(
        swing_policy=swing_policy,
        accumulation_screener_config=accumulation_config,
        min_net_buy_days=1,
        hard_filter_policy=production_policy_bundle.hard_filter_policy,
        disable_score_filters=True,
    )

    def _evaluate_market_context_for_corpus(*, as_of_date: date) -> MarketContext:
        return evaluate_market_context(
            db_path=resolved_db,
            as_of_date=as_of_date,
            universe=universe,
        )

    # ADR-068 authoritative cohort identity. Resolved from the exact typed
    # policy objects injected into the engines above — the adapter reads no
    # config file for identity and performs no hashing. The application service
    # owns the whole formula; the adapter only echoes it for the operator.
    cohort_identity = resolve_accumulation_cohort_identity(
        accum_score_policy=production_policy_bundle.accum_score_policy,
        signal_engine_config=production_policy_bundle.signal_engine_config,
        structural_gates=production_policy_bundle.structural_gates,
        execution_gates=production_policy_bundle.execution_gates,
        hard_filter_policy=production_policy_bundle.hard_filter_policy,
        unevaluable_gate_policy=production_policy_bundle.unevaluable_gate_policy,
    )
    observation_identity = LeanObservationIdentity(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=cohort_identity.semantic_compatibility_id,
    )
    _echo_cohort_identity(cohort_identity)

    learning_repo = SQLiteLearningArtifactRepository(resolved_db)
    # ADR-068 slice 5: informational fork warning only (not a hard block).
    # Cron re-enable is owned by a later task; capture still proceeds.
    try:
        existing_obs = learning_repo.list_observations(AssessmentPurpose.ACCUMULATION_DISCOVERY)
        counts: dict[str, int] = {}
        for obs in existing_obs:
            key = (obs.compatibility_id or "").strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
        warning = assess_cohort_fork_warning(
            next_compatibility_id=str(cohort_identity.semantic_compatibility_id),
            observation_counts_by_compat=counts,
        )
        if warning is not None:
            typer.echo(f"[cohort-fork] {warning.message}", err=True)
            typer.echo(
                f"[cohort-fork] orphan_observation_count={warning.orphan_observation_count} "
                f"existing_cohort_count={warning.existing_cohort_count}",
                err=True,
            )
    except (LearningContractError, LearningArtifactReadIntegrityError, OSError) as exc:
        typer.echo(
            f"[cohort-fork] warning unavailable ({type(exc).__name__}: {exc})",
            err=True,
        )
    try:
        EnsureAccumulationPolicySnapshotsUseCase(learning_repo).execute(
            EnsureAccumulationPolicySnapshotsRequest(
                observation_identity=observation_identity,
                accum_score_policy=production_policy_bundle.accum_score_policy,
                signal_engine_config=production_policy_bundle.signal_engine_config,
                structural_gates=production_policy_bundle.structural_gates,
                execution_gates=production_policy_bundle.execution_gates,
                hard_filter_policy=production_policy_bundle.hard_filter_policy,
                unevaluable_gate_policy=production_policy_bundle.unevaluable_gate_policy,
                created_at=datetime.now(timezone.utc),
                source_revision=resolve_producer_source_revision(),
            )
        )
    except LearningContractError as exc:
        typer.echo(f"[error] production policy snapshot ensure failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    if named_tickers is None:
        # Board-wide pure candle-active still needs a named roster digest for
        # Option A population binding; use the resolved membership roster of the
        # run is not available here — require an explicit named universe for
        # challenge corpus capture. Fall back to empty is rejected by use case.
        typer.echo(
            "[error] population binding (schema-10) requires a named universe "
            "(e.g. lq45); 'cached' board-wide mode is not challenge-corpus authority.",
            err=True,
        )
        raise typer.Exit(1)

    return BackfillSignalObservationsUseCase(
        record_observations_use_case=screen_bundle.record_observations_use_case,
        screen_request_builder=screen_request_builder,
        market_data_repository=market_repo,
        observation_identity=observation_identity,
        membership_resolver=membership_resolver,
        pit_window_sessions=pit_window,
        named_universe_tickers=named_tickers,
        producer_source_revision=resolve_producer_source_revision(),
        population_name=universe if universe != "cached" else "lq45",
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
