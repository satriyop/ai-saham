"""
Daily briefing command.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console, Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_market_context_display import (
    REGIME_DISPLAY_LABEL,
    context_conviction_score,
    context_factor_value,
    context_regime_style,
)
from src.application.services.market_context_engine import MarketContextEngine
from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingUseCase,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_config import load_market_context_config
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        typer.echo(f"Invalid date format: {value} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)


def today(
    universe: Annotated[
        Optional[str], typer.Option("--universe", "-u", help="Universe to brief"),
    ] = None,
    top: Annotated[int, typer.Option("--top", help="Number of candidates per section", min=1)] = 3,
    date_str: Annotated[Optional[str], typer.Option("--date", help="Date YYYY-MM-DD")] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Show a read-only daily briefing from local cached data.

    This command does not fetch, tune, or write data. Use `saham fetch ...` and
    `saham screen ...` when you need to update inputs.
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
        ),
        universe_loader=YamlUniverseConfigLoader(),
    )

    response = use_case.execute(
        DailyBriefingRequest(
            universe=universe,
            top=top,
            as_of_date=as_of,
        )
    )

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
        summary.add_row("Market", market_text)
    else:
        summary.add_row("Mode", f"HISTORICAL — {response.live_session_date.isoformat()}")

    summary.add_row("Live session date", response.live_session_date.isoformat())
    latest_eod_str = (
        response.latest_completed_eod_date.isoformat()
        if response.latest_completed_eod_date
        else "-"
    )
    summary.add_row("Latest completed EOD", latest_eod_str)
    opening_date_str = (
        response.opening_snapshot_date.isoformat()
        if response.opening_snapshot_date
        else "-"
    )
    summary.add_row("Opening snapshot date", opening_date_str)

    summary.add_row("Universe", f"{response.universe.upper()} ({response.universe_count} tickers)")
    summary.add_row("Cached candles current", f"{fresh_count}/{response.universe_count}")

    if response.regime is not None:
        ctx = response.regime
        label = REGIME_DISPLAY_LABEL.get(ctx.regime.value, ctx.regime.value)
        score = context_conviction_score(ctx)
        style = context_regime_style(ctx)
        regime_text = f"[{style}]{label} ({score}/7)[/{style}]"
        summary.add_row("Market regime", regime_text)

        breadth = context_factor_value(ctx, "idx_breadth")
        if breadth is not None:
            summary.add_row("Breadth above SMA20", f"{breadth:.1f}%")

    opening = compact_table()
    opening.add_column("Ticker", style="bold")
    opening.add_column("Opening Setup")
    opening.add_column("IEV", justify="right")
    opening.add_column("IEP", justify="right")
    opening.add_column("Trend")
    if response.opening_candidates:
        for candidate in response.opening_candidates:
            iev = f"{candidate.iev:,}" if candidate.iev is not None else "-"
            iep = f"{candidate.iep:,}" if candidate.iep is not None else "-"

            # Color the opening-session setup label.
            setup_style = "green" if candidate.opening_setup == "PRIME" else (
                "yellow" if candidate.opening_setup == "WATCH" else "red"
            )
            setup_text = f"[{setup_style}]{candidate.opening_setup}[/{setup_style}]"

            trend_map = {"UP": "green", "DOWN": "red", "SIDE": "yellow"}
            trend_style = trend_map.get(str(candidate.trend).upper(), "white")
            trend_text = f"[{trend_style}]{candidate.trend or '-'}[/{trend_style}]"

            opening.add_row(candidate.ticker, setup_text, iev, iep, trend_text)
    else:
        opening.add_row(
            "-", "No saved opening snapshot", "-", "-", "Run: saham learn snapshot --force",
        )

    accumulation = compact_table()
    accumulation.add_column("Ticker", style="bold")
    accumulation.add_column("Score", justify="right")
    accumulation.add_column("Streak", justify="right")
    accumulation.add_column("Trend")
    if response.accumulation_candidates:
        for candidate in response.accumulation_candidates:
            trend_map = {"UP": "green", "DOWN": "red", "SIDE": "yellow"}
            trend_style = trend_map.get(str(candidate.trend).upper(), "white")
            trend_text = f"[{trend_style}]{candidate.trend or '-'}[/{trend_style}]"

            # Color score (0-100 scale, see ADR-039)
            if candidate.foreign_flow_score >= 66.7:
                score_style = "green"
            elif candidate.foreign_flow_score >= 50.0:
                score_style = "yellow"
            else:
                score_style = "white"
            score_text = f"[{score_style}]{candidate.foreign_flow_score:.1f}[/{score_style}]"

            accumulation.add_row(
                candidate.ticker,
                score_text,
                str(candidate.consecutive_streak),
                trend_text,
            )
    else:
        accumulation.add_row("-", "-", "-", "Run: saham screen accum --universe lq45")

    sections = [
        Text("Data & Regime", style="bold cyan"),
        summary,
        Text("Top Pre-Open Candidates", style="bold cyan"),
        opening,
        Text("Top Accumulation Candidates", style="bold cyan"),
        accumulation,
    ]

    if response.warnings:
        warnings = compact_table(show_header=False)
        warnings.add_column("Warning")
        for warning in response.warnings[:5]:
            warnings.add_row(f"- {warning}")
        sections.extend([Text("Warnings", style="bold yellow"), warnings])

    if response.stale_count > 0:
        next_action = (
            f"Next: Run 'saham fetch market --universe {response.universe}' to update, "
            f"then: saham screen accum --universe {response.universe} | saham analyze swing TICKER"
        )
        next_style = "bold yellow"
    else:
        next_action = (
            f"Next: saham screen accum --universe {response.universe} | "
            f"saham analyze swing TICKER"
        )
        next_style = "bold"

    sections.append(Text(next_action, style=next_style))
    console.print(
        panel(
            Group(*sections),
            title=f"Daily Briefing - {response.live_session_date.isoformat()}",
            subtitle=response.universe.upper(),
        )
    )
