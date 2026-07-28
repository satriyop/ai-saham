"""
Daily briefing command.

Layer: Adapter
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console, Group
from rich.text import Text

from src.adapters.cli.plan_swing_command_config import (
    load_plan_swing_command_config,
)
from src.adapters.cli.plan_swing_workflow_factory import (
    create_swing_analysis_workflow,
)
from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_market_context_display import (
    context_factor_value,
    context_regime_style,
)
from src.adapters.composition.accumulation_risk_workflow_factory import (
    create_accumulation_assess_risk_use_case,
)
from src.adapters.composition.stock_analysis_workflow_dependencies import (
    create_stock_analysis_workflow_dependencies,
)
from src.application.services.market_context_engine import MarketContextEngine
from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.daily_accumulation_projection import (
    DailyAccumulationCandidate,
)
from src.application.use_case.daily_briefing_use_case import (
    CORP_ACTION_LOOKAHEAD_DAYS,
    CorpActionBriefingRow,
    DailyBriefingRequest,
    DailyBriefingResponse,
    DailyBriefingUseCase,
    OpeningBriefingCandidate,
)
from src.application.use_case.daily_setup_lens_impact_use_case import (
    DailySetupLensImpactUseCase,
    SwingLensRequestDefaults,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.composition.signal_engine_factory import create_signal_engine
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_config import load_market_context_config
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        typer.echo(f"Invalid date format: {value} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)


def _action_style(opening_setup) -> tuple[str, str]:
    """Return (label, rich-style) for a pre-open TradeSetup action."""
    from src.domain.value_objects.trade_setup import SetupAction

    action = SetupAction.from_value(opening_setup)
    if action is SetupAction.ENTER:
        style = "green"
    elif action is SetupAction.WATCH:
        style = "yellow"
    elif action is not None and action.is_blocked:
        style = "red"
    else:
        style = "dim"
    label = action.value if action is not None else str(opening_setup or "?")
    return label, style


def _gap_pct_text(gap: str | None) -> str:
    if gap is None:
        return ""
    sign = "" if gap.startswith(("-", "+")) else "+"
    return f" ({sign}{gap}%)"


def _opening_candidate_lines(candidate: OpeningBriefingCandidate) -> list[Text]:
    """Compact multi-line pre-open decision context from the capture corpus."""
    label, style = _action_style(candidate.opening_setup)

    # Line 1 — verdict: ticker · action [· blocking gates] · signal · trend
    head = Text()
    head.append(f"{candidate.ticker}  ", style="bold")
    head.append(label, style=style)
    if candidate.blocking_gates:
        head.append(f" · {', '.join(candidate.blocking_gates)}", style="red")
    if candidate.signal_score is not None:
        strength = f" {candidate.signal_strength}" if candidate.signal_strength else ""
        head.append(f"  sig {candidate.signal_score}{strength}", style="cyan")
    if candidate.trend_signal:
        trend_style = {"BULLISH": "green", "BEARISH": "red"}.get(
            str(candidate.trend_signal).upper(), "yellow"
        )
        head.append(f"  {candidate.trend_signal}", style=trend_style)

    # Line 2 — auction: IEV (+ Δ vs 08:56 lock) · IEP (+ gap%)
    auction = Text("  ")
    if candidate.iev is not None:
        auction.append(f"IEV {candidate.iev:,}")
        if candidate.delta_iev is not None:
            auction.append(f" (Δ{candidate.delta_iev:+,} vs 08:56)", style="magenta")
    if candidate.iep is not None:
        auction.append(f"  IEP {candidate.iep:,}{_gap_pct_text(candidate.iep_gap_pct)}")

    # Line 3 — microstructure: imbalance · entry/stop · broker backing
    micro_parts: list[str] = []
    if candidate.bid_offer_imbalance is not None:
        arrow = "▲bid" if candidate.bid_offer_imbalance >= 0.5 else "▼offer"
        micro_parts.append(f"imbalance {candidate.bid_offer_imbalance:.2f} {arrow}")
    if candidate.entry_price is not None and candidate.stop_loss_price is not None:
        micro_parts.append(f"entry {candidate.entry_price}/stop {candidate.stop_loss_price}")
    if candidate.broker_backing_score is not None:
        tag = f" {candidate.broker_backing_tag}" if candidate.broker_backing_tag else ""
        micro_parts.append(f"backing {candidate.broker_backing_score:.0f}{tag}")

    lines = [head]
    if str(auction).strip():
        lines.append(auction)
    if micro_parts:
        lines.append(Text("  " + " · ".join(micro_parts), style="dim"))
    return lines


def _opening_table(candidates: list[OpeningBriefingCandidate]):
    """Render pre-open candidates as compact multi-line decision blocks."""
    elements: list = []
    for candidate in candidates:
        elements.extend(_opening_candidate_lines(candidate))
    return Group(*elements)


def _corp_action_elements(
    rows: list[CorpActionBriefingRow],
    universe: str,
    live_session_date: date,
) -> list:
    """Render the CORPORATE ACTIONS section, emphasizing today/tomorrow milestones."""
    from datetime import timedelta

    title = Text(
        f"CORPORATE ACTIONS — {universe.upper()}, next {CORP_ACTION_LOOKAHEAD_DAYS}d",
        style="bold cyan",
    )
    if not rows:
        return [title, Text("No upcoming corporate actions in window.", style="dim")]

    tomorrow = live_session_date + timedelta(days=1)
    table = compact_table()
    table.add_column("Ticker", style="bold")
    table.add_column("Type")
    table.add_column("Date-role")
    table.add_column("Date")
    table.add_column("Note")
    for row in rows[:12]:
        if row.event_date == live_session_date:
            date_text = "[bold yellow]TODAY[/bold yellow]"
        elif row.event_date == tomorrow:
            date_text = "[yellow]tomorrow[/yellow]"
        else:
            date_text = row.event_date.isoformat()
        note = (row.note or "-")[:40]
        table.add_row(row.ticker, row.event_type, row.date_role, date_text, note)
    return [title, table]


_RISK_STATUS_STYLE = {"OPEN": "green", "BLOCK": "red", "UNKNOWN": "white"}


def _accumulation_screen_table(candidates: list[DailyAccumulationCandidate]):
    table = compact_table()
    table.add_column("Ticker", style="bold")
    table.add_column("Flow", justify="right")
    table.add_column("Phase")
    table.add_column("Signal", justify="right")
    table.add_column("Authority", justify="right")
    table.add_column("Risk")
    table.add_column("Action")
    for candidate in candidates:
        flow_text = f"{candidate.accum_score:.1f}"
        phase_text = candidate.setup_phase or "-"
        signal_text = str(candidate.signal_score) if candidate.signal_score is not None else "-"
        coverage_text = (
            f"{candidate.signal_authority_coverage:.0%}"
            if candidate.signal_authority_coverage is not None
            else "-"
        )
        risk_style = _RISK_STATUS_STYLE.get(candidate.risk_status, "white")
        risk_text = f"[{risk_style}]{candidate.risk_status}[/{risk_style}]"
        action_text = candidate.action or "-"

        table.add_row(
            candidate.ticker,
            flow_text,
            phase_text,
            signal_text,
            coverage_text,
            risk_text,
            action_text,
        )
    return table


# A regime call below this confidence is near a boundary — treat it as noise.
LOW_REGIME_CONFIDENCE = 0.30


def _market_regime_text(ctx) -> str:
    head = ctx.regime.value
    days_in_regime = getattr(ctx, "days_in_regime", None)
    if days_in_regime is not None:
        head = f"{head} for {days_in_regime}d"
    parts = [head, f"conviction {float(ctx.conviction):.2f}"]

    if ctx.regime_confidence is not None:
        conf = float(ctx.regime_confidence)
        label = f"confidence {conf:.2f}"
        if conf < LOW_REGIME_CONFIDENCE:
            # Flag low-confidence regimes so a near-coin-flip call is not read
            # with the same weight as a decisive one.
            label += " ⚠ low"
        parts.append(label)

    if ctx.regime_stability is not None:
        parts.append(f"stability {ctx.regime_stability}")

    if ctx.transition_warning:
        parts.append(f"transition: {ctx.transition_warning}")

    return " | ".join(parts)


def _build_setup_lens_impact_use_case(
    *,
    db_path: Path,
    cfg,
) -> DailySetupLensImpactUseCase:
    """Adapter wiring: build the 4 canonical setup-bound swing workflows and
    inject them (plus typed request defaults) into the read-only impact use case.

    This mirrors plan_swing_commands.py construction exactly; it introduces no
    fetch/cache/scoring policy of its own.
    """
    swing_cmd_cfg = load_plan_swing_command_config()
    swing_config = swing_cmd_cfg.swing_config
    analyze_config = swing_cmd_cfg.analyze_swing_config

    smart_money_brokers = set(swing_config.smart_money_brokers)
    noise_brokers = set(swing_config.noise_brokers)
    broker_weights: dict[str, Decimal] = {
        **{code: swing_config.smart_weight for code in smart_money_brokers},
        **{code: swing_config.noise_weight for code in noise_brokers},
    }

    deps = create_stock_analysis_workflow_dependencies(db_path)
    setup_workflows = {
        setup_name: create_swing_analysis_workflow(
            db_path=db_path,
            setup_name=setup_name,
            swing_config=swing_config,
            analyze_config=analyze_config,
            smart_money_brokers=smart_money_brokers,
            noise_brokers=noise_brokers,
            broker_weights=broker_weights,
            dependencies=deps,
        )
        for setup_name in AVAILABLE_SWING_SETUPS
    }

    request_defaults = SwingLensRequestDefaults(
        window=cfg.swing.window,
        flow_window=analyze_config.flow_detail_window_sessions,
        risk_pct=cfg.swing.risk_pct,
        atr_mult=cfg.swing.atr_mult,
        rr=cfg.swing.rr,
        regime_universe=cfg.analysis.regime_universe,
        benchmark=cfg.analysis.benchmark,
        db_path=db_path,
    )

    return DailySetupLensImpactUseCase(
        setup_workflows=setup_workflows,
        request_defaults=request_defaults,
    )


@dataclass(frozen=True)
class SetupLensImpactRender:
    elements: list
    rendered_next_commands: bool


def _setup_lens_impact_elements(setup_lens_impact) -> SetupLensImpactRender:
    """Render the SETUP LENS IMPACT section from the pre-computed result DTO.

    Rendering only: reads fields already on the result/row/cell; computes no
    action, match, entry-authority, or capping.
    """
    elements: list = [Text("SETUP LENS IMPACT", style="bold cyan")]

    if setup_lens_impact is None or not setup_lens_impact.rows:
        elements.append(Text("No accumulation candidates to evaluate."))
        return SetupLensImpactRender(elements, rendered_next_commands=False)

    table = compact_table()
    table.add_column("Ticker", style="bold")
    table.add_column("Base")
    for setup_name in AVAILABLE_SWING_SETUPS:
        table.add_column(setup_name)

    for row in setup_lens_impact.rows:
        cells_by_setup = {cell.setup_name: cell for cell in row.cells}
        row_values = [row.ticker, row.base_action or "-"]
        for setup_name in AVAILABLE_SWING_SETUPS:
            cell = cells_by_setup.get(setup_name)
            if cell is None:
                row_values.append("-")
                continue
            if cell.warning is not None:
                # Plain Text so the literal "[warning: ...]" is not parsed as
                # rich markup and stripped.
                row_values.append(Text(f"[warning: {cell.warning}]"))
                continue
            score_text = str(cell.signal_score) if cell.signal_score is not None else "-"
            text = f"{cell.action or '-'} {score_text} {cell.setup_match}"
            if cell.capped_reason:
                text += "(no-entry)"
            row_values.append(text)
        table.add_row(*row_values)

    elements.append(table)

    next_lines: list[str] = []
    for row in setup_lens_impact.rows:
        for cell in row.cells:
            if cell.warning is None and cell.action in ("ENTER", "WATCH"):
                next_lines.append(f"  saham plan swing {row.ticker} --setup {cell.setup_name}")
    rendered_next = bool(next_lines)
    if next_lines:
        elements.append(Text("Next:", style="bold"))
        for line in next_lines:
            elements.append(Text(line))

    return SetupLensImpactRender(elements, rendered_next_commands=rendered_next)


def _fallback_next_command(response) -> str:
    if response.overall_authority == "NOT_READY":
        # A3: name the dataset actually blocking readiness so the user isn't told to
        # re-fetch candles that are already complete.
        gaps = [
            f"{item.dataset} {item.coverage_count}/{item.total_count}"
            for item in response.readiness_items
            if item.status in ("NOT_READY", "UNAVAILABLE")
        ]
        gap_note = f"  ({', '.join(gaps)} stale)" if gaps else ""
        return f"Next: saham fetch market --universe {response.universe}{gap_note}"

    if response.daily_accumulation_candidates:
        ticker = response.daily_accumulation_candidates[0].ticker
        return f"Next: saham plan swing {ticker}"

    return f"Next: saham screen accum --universe {response.universe}"


# ── Live-first briefing resolution (ADR-052) ──────────────────────────────────
#
# `today` is a live-first adapter surface: it refreshes its own inputs by reusing
# the existing RefreshDailyWorkspaceUseCase (fetch writes cache, briefing renders
# from cache), then degrades to a cached render on failure/offline/lock-window.
# The adapter owns NO fetch/cache policy — it only selects the path and maps errors.
#
# The refresh runs synchronously in the foreground: with refresh=False the fetch
# workflow only pulls stale/missing tickers, so steady-state runs are quick and the
# one-time backfill is the only slow run. Per-request HTTP timeouts (Stockbit/IDX)
# bound total latency, so no wall-clock guard is needed; `--offline` skips it.


@dataclass(frozen=True)
class _BriefingResolution:
    data_source: str  # LIVE | CACHED | LOCK_WINDOW | HISTORICAL
    response: DailyBriefingResponse
    extra_warnings: list[str]


def _build_refresh_workspace_use_case(*, use_case: DailyBriefingUseCase, db_path: Path):
    """Adapter wiring: adapt RefreshDailyWorkspaceRequest → the fetch-market workflow
    and pair it with the already-constructed briefing use case. No fetch policy here.
    """
    from src.adapters.cli.fetch_market_provider_factory import create_broker_provider
    from src.application.use_case.fetch_market_command_workflow_use_case import (
        FetchMarketCommandWorkflowRequest,
    )
    from src.application.use_case.refresh_daily_workspace_use_case import (
        RefreshDailyWorkspaceUseCase,
    )
    from src.infrastructure.composition.fetch_market.fetch_market_workflow_factory import (
        create_workflow_use_case,
    )
    from src.infrastructure.config.data_sources_config import candle_source

    broker_provider_obj, broker_provider_name = create_broker_provider(None)
    workflow = create_workflow_use_case(
        db_path=db_path,
        broker_provider=broker_provider_obj,
        broker_provider_name=broker_provider_name,
    )

    def refresh_capability(req, *, on_start=None, on_ticker_complete=None):
        workflow_request = FetchMarketCommandWorkflowRequest(
            tickers=list(req.tickers),
            universe=req.universe,
            days=req.days,
            db_path=db_path,
            candles_provider=candle_source(),
            broker_provider=broker_provider_obj,
            broker_provider_name=broker_provider_name,
            refresh=req.force_refresh,
            candles_only=req.components == "CANDLES_ONLY",
            broker_only=req.components == "BROKER_ONLY",
            no_meta=not req.include_meta,
            no_enrichment=not req.include_enrichment,
            no_calendar=not req.include_calendar,
        )
        return workflow.execute(
            workflow_request,
            on_ticker_complete=on_ticker_complete,
            on_start=on_start,
        )

    return RefreshDailyWorkspaceUseCase(
        refresh_market_data_capability=refresh_capability,
        daily_briefing_use_case=use_case,
    )


def _resolve_briefing_response(
    *,
    use_case: DailyBriefingUseCase,
    request: DailyBriefingRequest,
    offline: bool,
    db_path: Path,
) -> _BriefingResolution:
    """Decide LIVE vs cached render and return the briefing with its provenance.

    Cache-only (no fetch) when: a historical `--date` is requested, `--offline` is
    set, or the market is in the pre-open NCP lock window (prefer the committed
    08:57 corpus decision). Otherwise refresh live and fall back to cache on any
    failure/timeout.
    """
    if request.as_of_date is not None:
        return _BriefingResolution("HISTORICAL", use_case.execute(request), [])
    if offline:
        return _BriefingResolution("CACHED", use_case.execute(request), [])

    from src.infrastructure.browser.stockbit_market_time import get_display_market_status

    pre_status = get_display_market_status()  # instant, no network
    if getattr(pre_status, "is_pre_open", False):
        # ADR-052 lock-window guard: do not probe live IEV during the NCP lock.
        return _BriefingResolution("LOCK_WINDOW", use_case.execute(request), [])

    typer.echo("⟳ Refreshing live data… (use --offline to skip)", err=True)
    try:
        refresh_uc = _build_refresh_workspace_use_case(use_case=use_case, db_path=db_path)
        from src.application.use_case.refresh_daily_workspace_use_case import (
            RefreshDailyWorkspaceRequest,
        )

        result = refresh_uc.execute(
            RefreshDailyWorkspaceRequest(
                universe=request.universe,
                briefing_top=request.top,
            )
        )
        return _BriefingResolution("LIVE", result.briefing, list(result.warnings))
    except Exception as exc:  # noqa: BLE001 — degrade to cache on any refresh failure
        return _BriefingResolution(
            "CACHED",
            use_case.execute(request),
            [f"Live refresh failed ({type(exc).__name__}) — showing cached data."],
        )


_DATA_SOURCE_STYLE = {
    "LIVE": "green",
    "CACHED": "yellow",
    "LOCK_WINDOW": "yellow",
    "HISTORICAL": "cyan",
}


def _data_source_text(resolution: _BriefingResolution) -> Text:
    label = {
        "LIVE": "LIVE — refreshed from providers",
        "CACHED": "CACHED — local data (⚠ may be stale)",
        "LOCK_WINDOW": "LOCK_WINDOW — committed pre-open decision (no live probe)",
        "HISTORICAL": "HISTORICAL — as-of date requested",
    }[resolution.data_source]
    style = _DATA_SOURCE_STYLE[resolution.data_source]
    return Text(label, style=style)


def today(
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe to brief"),
    ] = None,
    top: Annotated[int, typer.Option("--top", help="Number of candidates per section", min=1)] = 3,
    date_str: Annotated[Optional[str], typer.Option("--date", help="Date YYYY-MM-DD")] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
    offline: Annotated[
        bool,
        typer.Option(
            "--offline/--no-offline",
            "--no-fetch",
            help="Skip the live refresh and render local cached data instantly.",
        ),
    ] = False,
) -> None:
    """
    Live-first daily briefing cockpit (ADR-052).

    Refreshes live-sensitive inputs (candles, broker flow, regime, calendar) then
    renders; degrades to cached data with a ⚠ marker on failure/offline. Use
    `--offline` for the instant cache-only read. During the pre-open NCP lock it
    shows the committed 08:57 decision (no live probe).

    Not TradeSetup authority — use `saham plan swing TICKER` for decisions.
    Regime detail: `saham inspect regime`.
    """
    cfg = load_app_config()
    universe = universe or cfg.analysis.universe
    db_path = db_path or Path(cfg.storage.db_path)
    console = Console()
    as_of = _parse_date(date_str)
    market_repo = SQLiteMarketRepository(db_path)
    broker_repo = SQLiteBrokerRepository(db_path)
    accumulation_config = load_accumulation_screener_config()
    try:
        regime_tickers = resolve_tickers(
            universe=cfg.analysis.regime_universe,
            explicit=[],
            db_path=db_path,
            loader=YamlUniverseConfigLoader(),
            repository=broker_repo,
        )
    except Exception:
        regime_tickers = []
    risk_use_case = create_accumulation_assess_risk_use_case(
        market_repository=market_repo,
    )
    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=MarketContextEngine(
            market_repository=market_repo,
            config=load_market_context_config(),
            broker_repository=broker_repo,
            universe=regime_tickers,
        ),
        accumulation_use_case=AccumulationScreenUseCase(
            broker_repository=broker_repo,
            market_repository=market_repo,
            indicator_registry=create_indicator_registry(),
            rules_loader=RulesYamlLoader(),
            derived_feature_policy=accumulation_config.derived_features,
            risk_use_case=risk_use_case,
            signal_engine=create_signal_engine(db_path=db_path, with_enrichment=True),
        ),
        universe_loader=YamlUniverseConfigLoader(),
        learning_observation_repository=SQLiteLearningArtifactRepository(db_path),
        setup_lens_impact_use_case=_build_setup_lens_impact_use_case(
            db_path=db_path,
            cfg=cfg,
        ),
        iev_baseline_repository=SQLiteIEVRepository(db_path),
        corp_action_repository=SQLiteCorporateActionCalendarRepository(db_path),
    )

    resolution = _resolve_briefing_response(
        use_case=use_case,
        request=DailyBriefingRequest(
            universe=universe,
            top=top,
            as_of_date=as_of,
        ),
        offline=offline,
        db_path=db_path,
    )
    response = resolution.response

    fresh_count = response.universe_count - response.stale_count
    summary = compact_table(show_header=False)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")

    # Style market status value / Mode row
    if not response.is_historical:
        from src.infrastructure.browser.stockbit_market_time import (
            get_display_market_status,
        )

        market_status = get_display_market_status()
        market_style = "green" if market_status.is_open else "yellow"
        market_text = Text()
        market_text.append(market_status.session_name, style=market_style)
        market_text.append("  ")
        market_text.append(f"[{market_status.source}]")
        if market_status.is_open:
            market_text.append("  ⚠ open")
        if market_status.source == "local_clock":
            # A2: the session was inferred from the local clock (no live market feed),
            # which has no IDX-holiday awareness — say so instead of implying certainty.
            market_text.append("  · clock-inferred; unverified on IDX holidays", style="dim yellow")
        summary.add_row("Market", market_text)
    else:
        summary.add_row("Mode", f"HISTORICAL — {response.live_session_date.isoformat()}")

    summary.add_row("Data source", _data_source_text(resolution))
    summary.add_row("Live session date", response.live_session_date.isoformat())
    latest_eod_str = (
        response.latest_completed_eod_date.isoformat()
        if response.latest_completed_eod_date
        else "-"
    )
    summary.add_row("Latest completed EOD", latest_eod_str)
    opening_date_str = (
        response.opening_snapshot_date.isoformat() if response.opening_snapshot_date else "-"
    )
    summary.add_row("Opening snapshot date", opening_date_str)

    summary.add_row("Universe", f"{response.universe.upper()} ({response.universe_count} tickers)")
    summary.add_row("Cached candles current", f"{fresh_count}/{response.universe_count}")

    if response.regime is not None:
        ctx = response.regime
        style = context_regime_style(ctx)
        regime_text = f"[{style}]{_market_regime_text(ctx)}[/{style}]"
        summary.add_row("Market regime", regime_text)

        breadth = context_factor_value(ctx, "idx_breadth")
        if breadth is not None:
            summary.add_row("Breadth above SMA20", f"{breadth:.1f}%")

    # Split universe-scoped rows into actionable vs observations
    actionable_rows = []
    observation_rows = []
    for candidate in response.opening_candidates:
        from src.domain.value_objects.trade_setup import SetupAction

        action = SetupAction.from_value(candidate.opening_setup)
        if action is not None and action.is_open_watchlist:
            actionable_rows.append(candidate)
        else:
            observation_rows.append(candidate)

    pre_open_elements = []
    pre_open_elements.append(Text("PRE-OPEN ASSESSMENT", style="bold cyan"))

    no_snapshot = response.opening_snapshot_date is None
    no_opening = not response.opening_candidates
    no_market = not response.market_wide_opening_observations
    if no_snapshot and no_opening and no_market:
        pre_open_elements.extend(
            [
                Text("No saved opening snapshot"),
                Text("Run: saham research pre-open capture"),
            ]
        )
    else:
        if not response.opening_candidates:
            pre_open_elements.extend(
                [
                    Text(f"NO ACTIONABLE {response.universe.upper()} SETUPS", style="bold red"),
                    Text("No universe-scoped pre-open observations"),
                ]
            )
        else:
            if actionable_rows:
                verdict_str = f"ACTIONABLE {response.universe.upper()} SETUPS"
                pre_open_elements.append(Text(verdict_str, style="bold green"))
                pre_open_elements.append(_opening_table(actionable_rows))
            else:
                verdict_str = f"NO ACTIONABLE {response.universe.upper()} SETUPS"
                pre_open_elements.append(Text(verdict_str, style="bold red"))

            if observation_rows:
                pre_open_elements.append(Text("Universe observations", style="bold cyan"))
                pre_open_elements.append(_opening_table(observation_rows))

    if response.market_wide_opening_observations:
        pre_open_elements.extend(
            [
                Text("Market-wide observations", style="bold cyan"),
                _opening_table(response.market_wide_opening_observations),
            ]
        )

    accumulation = _accumulation_screen_table(response.daily_accumulation_candidates)

    # Build Data Readiness table
    readiness_table = compact_table()
    readiness_table.add_column("Dataset")
    readiness_table.add_column("Status")
    readiness_table.add_column("Coverage", justify="right")
    readiness_table.add_column("Required As Of")
    readiness_table.add_column("Reason")

    status_styles = {
        "READY": "green",
        "PARTIAL": "yellow",
        "NOT_READY": "red",
        "UNAVAILABLE": "red",
    }

    if response.readiness_items:
        for item in response.readiness_items:
            style = status_styles.get(item.status, "white")
            status_text = f"[{style}]{item.status}[/{style}]"
            coverage_text = f"{item.coverage_count}/{item.total_count}"
            req_as_of = item.required_as_of.isoformat() if item.required_as_of else "-"
            reason_text = item.reason or "-"
            readiness_table.add_row(
                item.dataset, status_text, coverage_text, req_as_of, reason_text
            )

    sections = [
        Text("Data & Regime", style="bold cyan"),
        summary,
        Text("Data Readiness", style="bold cyan"),
        readiness_table,
    ]
    sections.extend(pre_open_elements)

    sections.extend(
        _corp_action_elements(
            response.upcoming_corp_actions,
            response.universe,
            response.live_session_date,
        )
    )

    # Section title for accumulation screen
    accum_title = Text("ACCUMULATION SCREEN", style="bold cyan")
    if response.overall_authority == "PARTIAL":
        accum_title = Text.assemble(
            ("ACCUMULATION SCREEN", "bold cyan"),
            ("   ⚠ PARTIAL DATA — verify readiness before acting", "bold yellow"),
        )

    sections.append(accum_title)
    if response.overall_authority == "NOT_READY":
        sections.append(Text("Suppressed — data readiness is NOT_READY", style="red"))
    else:
        summary_row = response.accumulation_summary
        if summary_row is not None:
            summary_line = (
                f"{summary_row.checked} checked | {summary_row.data_ready} data-ready | "
                f"{summary_row.flow_candidates} flow candidates | "
                f"{summary_row.watch_count} WATCH | {summary_row.enter_count} ENTER | "
                f"{summary_row.blocked_count} blocked"
            )
            if summary_row.unclassified_count > 0:
                summary_line += f" | {summary_row.unclassified_count} unclassified"
            sections.append(Text(summary_line))

        if response.daily_accumulation_candidates:
            sections.append(accumulation)
        else:
            sections.append(Text("No accumulation candidates after canonical projection"))

    setup_lens_render = _setup_lens_impact_elements(response.setup_lens_impact)
    sections.extend(setup_lens_render.elements)

    # Live-refresh warnings (ADR-052) lead so a fallback-to-cache is visible first.
    all_warnings = resolution.extra_warnings + list(response.warnings)
    if all_warnings:
        warnings = compact_table(show_header=False)
        warnings.add_column("Warning")
        for warning in all_warnings[:5]:
            warnings.add_row(f"- {warning}")
        sections.extend([Text("Warnings", style="bold yellow"), warnings])

    if not setup_lens_render.rendered_next_commands:
        sections.append(Text(_fallback_next_command(response), style="bold"))
    console.print(
        panel(
            Group(*sections),
            title=f"Daily Briefing - {response.live_session_date.isoformat()}",
            subtitle=response.universe.upper(),
        )
    )
