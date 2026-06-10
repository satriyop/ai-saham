"""
CLI commands for pre-open market screening.

Provides the 'saham screen pre-open' command which orchestrates the
7-step pre-open screening workflow using browser data + AI research.

Usage patterns:

  # Claude Code supplies browser data via flags after navigating Stockbit:
  saham screen pre-open \\
    --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
    --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

  # Override config defaults at runtime:
  saham screen pre-open --movers-json '...' --iev-min 150000 --capital 5000000

  # No flags → prints browser action plan for Claude Code to follow:
  saham screen pre-open

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer
import yaml

from src.application.services.bootstrap import create_indicator_registry
from src.application.use_case.pre_open_screen import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenUseCase,
)
from src.domain.ports.browser_data_provider import BrowserInteractionRequired
from src.domain.value_objects.screener_result import ScreenerCandidate
from src.infrastructure.browser.stockbit_browser import (
    ManualBrowserDataProvider,
    StockbitBrowserInstructionsProvider,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

screen_app = typer.Typer(
    name="screen",
    help="Pre-open market screening commands",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")
DEFAULT_STRATEGY_PATH = Path("strategies/pre-open-screener/strategy.yaml")
DEFAULT_SESSION_FILE = Path("stockbit_session.json")


def _playwright_available() -> bool:
    """Return True if playwright is installed."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _session_exists() -> bool:
    return DEFAULT_SESSION_FILE.exists()


def _load_config(strategy_path: Path, overrides: dict) -> PreOpenScreenConfig:
    """Load config from YAML, apply CLI overrides."""
    if strategy_path.exists():
        with open(strategy_path) as f:
            data = yaml.safe_load(f)
        config = PreOpenScreenConfig.from_yaml(data)
    else:
        config = PreOpenScreenConfig()

    if "iev_min" in overrides and overrides["iev_min"] is not None:
        config.iev_min = overrides["iev_min"]
    if "capital" in overrides and overrides["capital"] is not None:
        config.capital = Decimal(str(overrides["capital"]))
    if "stop_loss_pct" in overrides and overrides["stop_loss_pct"] is not None:
        config.stop_loss_pct = Decimal(str(overrides["stop_loss_pct"]))
    if "tick_above" in overrides and overrides["tick_above"] is not None:
        config.tick_above = overrides["tick_above"]

    return config


def _print_browser_plan(config: PreOpenScreenConfig) -> None:
    """Print a step-by-step plan for Claude Code to execute via browser tools."""
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo("BROWSER ACTION PLAN — Pre-Open Screener")
    typer.echo("=" * 60)
    typer.echo("")
    typer.echo("Claude Code: execute these steps, then re-run this command")
    typer.echo("with --movers-json and --order-books-json flags.")
    typer.echo("")
    typer.echo("STEP 1 — Fetch IEV Movers from Stockbit")
    typer.echo("-" * 40)
    typer.echo("  URL: https://stockbit.com/#/screener")
    typer.echo('  1. Go to Screener → Movers section, click "Selengkapnya"')
    typer.echo("  2. Sort by IEV column, descending")
    typer.echo(f"  3. Collect all rows with IEV >= {config.iev_min:,}")
    typer.echo("  4. Build JSON array:")
    typer.echo('     [{"ticker": "BBCA", "iev": 150000}, ...]')
    typer.echo("")
    typer.echo("STEP 2 — Fetch Order Books (for each ticker from Step 1)")
    typer.echo("-" * 40)
    typer.echo("  URL: https://stockbit.com/#/stock/{TICKER}/orderbook")
    typer.echo("  1. For each ticker: open order book tab")
    typer.echo("  2. Find the BID row with the LARGEST volume (lots)")
    typer.echo("  3. Record price and volume")
    typer.echo("  4. Build JSON object:")
    typer.echo('     {"BBCA": {"price": 8900, "volume": 50000}, ...}')
    typer.echo("")
    typer.echo("STEP 3 — Re-run with collected data")
    typer.echo("-" * 40)
    typer.echo("  saham screen pre-open \\")
    typer.echo("    --movers-json '<step1_json>' \\")
    typer.echo("    --order-books-json '<step2_json>'")
    typer.echo("")
    typer.echo("=" * 60)


def _display_results(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
) -> None:
    """Render the screener results as a formatted terminal report."""
    typer.echo("")
    typer.echo("=" * 72)
    typer.echo("PRE-OPEN SCREENER RESULTS")
    typer.echo("=" * 72)
    typer.echo(f"Date: {screened_date}   IEV filter: >= {iev_min:,}")
    typer.echo(f"Movers evaluated: {total_movers_seen}   Candidates: {len(candidates)}")
    typer.echo("")

    if not candidates:
        typer.echo("No candidates passed the IEV filter.")
        return

    # Header row
    col = "{:<8} {:>10} {:>10} {:>10} {:>9} {:>10} {:<8}"
    typer.echo(
        col.format("TICKER", "IEV", "ENTRY", "STOP-LOSS", "STOP%", "CAPITAL", "TREND")
    )
    typer.echo("-" * 72)

    for c in candidates:
        entry = f"{c.entry_price:,.0f}" if c.entry_price else "—"
        stop = f"{c.stop_loss_price:,.0f}" if c.stop_loss_price else "—"
        stop_pct = c.risk_reward_label if c.has_entry_plan else "—"
        capital = f"{c.capital:,.0f}"
        trend = c.trend_signal or "—"
        rsi_tag = f" RSI:{c.rsi:.0f}" if c.rsi else ""

        typer.echo(
            col.format(c.ticker, f"{c.iev:,}", entry, stop, stop_pct, capital, trend + rsi_tag)
        )

    typer.echo("-" * 72)

    # AI summaries (if available)
    has_ai = any(c.ai_summary for c in candidates)
    if has_ai:
        typer.echo("")
        typer.echo("AI RESEARCH SUMMARIES")
        typer.echo("-" * 72)
        for c in candidates:
            if c.ai_summary:
                typer.echo(f"\n[{c.ticker}]")
                typer.echo(c.ai_summary)

    # Warnings
    if warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for w in warnings:
            typer.echo(f"  ! {w}")

    typer.echo("")
    typer.echo("DISCLAIMER: Analysis only. Not trading advice.")
    typer.echo("=" * 72)


@screen_app.command("pre-open")
def pre_open(
    movers_json: Annotated[
        Optional[str],
        typer.Option(
            "--movers-json",
            help='Pre-fetched movers as JSON: \'[{"ticker":"BBCA","iev":150000}]\'',
        ),
    ] = None,
    order_books_json: Annotated[
        Optional[str],
        typer.Option(
            "--order-books-json",
            help='Pre-fetched order books as JSON: \'{"BBCA":{"price":8900,"volume":50000}}\'',
        ),
    ] = None,
    iev_min: Annotated[
        Optional[int],
        typer.Option("--iev-min", help="Override IEV minimum threshold", min=1),
    ] = None,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", help="Override entry capital in IDR", min=1),
    ] = None,
    stop_loss: Annotated[
        Optional[float],
        typer.Option("--stop-loss", help="Override stop-loss fraction (e.g. 0.15 for 15%)"),
    ] = None,
    tick_above: Annotated[
        Optional[int],
        typer.Option("--tick-above", help="Override ticks above best bid for entry", min=1),
    ] = None,
    strategy_path: Annotated[
        Optional[Path],
        typer.Option("--strategy", "-s", help="Path to screener strategy.yaml"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
    ] = None,
    with_ai: Annotated[
        bool,
        typer.Option("--with-ai", help="Enable AI research per candidate (requires ANTHROPIC_API_KEY)"),
    ] = False,
    provider: Annotated[
        Optional[str],
        typer.Option("--provider", help="AI provider for research (claude/openai)"),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run Playwright headless (default) or visible"),
    ] = True,
) -> None:
    """
    Run the pre-open market screener for IDX stocks.

    Screens Stockbit movers for high IEV, computes entry/stop-loss from
    the order book, and optionally runs AI research on each candidate.

    Workflow:
      Auto-mode (playwright installed + session saved): runs fully autonomously.
      With --movers-json: runs full analysis using pre-fetched browser data.
      Without flags: prints browser action plan for Claude Code to follow.

    Examples:
        # Autonomous (requires: pip install playwright && saham screen save-session):
        saham screen pre-open

        # Print browser action plan (Claude Code reads and executes):
        saham screen pre-open

        # Run with Claude Code-provided browser data:
        saham screen pre-open \\
          --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
          --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

        # Override thresholds:
        saham screen pre-open --movers-json '...' --iev-min 150000 --capital 5000000

        # With AI research:
        saham screen pre-open --movers-json '...' --with-ai
    """
    resolved_strategy = strategy_path or DEFAULT_STRATEGY_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    # Load config with CLI overrides
    config = _load_config(
        strategy_path=resolved_strategy,
        overrides={
            "iev_min": iev_min,
            "capital": capital,
            "stop_loss_pct": stop_loss,
            "tick_above": tick_above,
        },
    )

    # No browser data supplied → try Playwright auto-mode, then fall back to plan
    if not movers_json:
        if _playwright_available() and _session_exists():
            typer.echo("Playwright session found — running autonomously...")
            from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider
            browser_provider = PlaywrightStockbitProvider(
                session_file=DEFAULT_SESSION_FILE,
                headless=headless,
            )
            # Skip JSON parsing, go straight to use-case wiring below
        else:
            if _playwright_available() and not _session_exists():
                typer.echo("Playwright installed but no session found.")
                typer.echo("Run: saham screen save-session")
                typer.echo("")
            typer.echo(f"Strategy: {resolved_strategy}")
            typer.echo(f"IEV threshold: {config.iev_min:,}")
            _print_browser_plan(config)
            raise typer.Exit(0)
    else:
        # Parse browser data provided via flags
        try:
            movers_raw = json.loads(movers_json)
            if not isinstance(movers_raw, list):
                typer.echo("Error: --movers-json must be a JSON array.", err=True)
                raise typer.Exit(1)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid JSON in --movers-json: {e}", err=True)
            raise typer.Exit(1)

        order_books_raw: dict | None = None
        if order_books_json:
            try:
                order_books_raw = json.loads(order_books_json)
            except json.JSONDecodeError as e:
                typer.echo(f"Error: Invalid JSON in --order-books-json: {e}", err=True)
                raise typer.Exit(1)

        typer.echo(f"Running pre-open screen ({len(movers_raw)} movers, IEV >= {config.iev_min:,})...")
        browser_provider = ManualBrowserDataProvider.from_json(movers_raw, order_books_raw)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    registry = create_indicator_registry()

    ai_explainer = None
    if with_ai:
        try:
            ai_explainer = _build_ai_researcher(provider=provider)
        except Exception as e:
            typer.echo(f"Warning: Could not initialize AI research: {e}", err=True)
            typer.echo("Continuing without AI research.", err=True)

    use_case = PreOpenScreenUseCase(
        browser=browser_provider,
        repository=repository,
        registry=registry,
        ai_explainer=ai_explainer,
    )

    try:
        request = PreOpenScreenRequest(config=config)
        response = use_case.execute(request)
        result = response.result

        _display_results(
            candidates=result.candidates,
            screened_date=result.screened_date,
            iev_min=result.iev_min,
            total_movers_seen=result.total_movers_seen,
            warnings=response.warnings,
        )

    except BrowserInteractionRequired as e:
        typer.echo(f"\nBrowser action required:", err=True)
        typer.echo(f"  URL: {e.url}", err=True)
        typer.echo(f"  {e.instructions}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Screener failed: {e}", err=True)
        raise typer.Exit(1)


def _build_ai_researcher(provider: Optional[str] = None):
    """Build a ticker researcher. Currently only Claude is supported."""
    from src.application.services.ai_research import ClaudeTickerResearcher

    if provider and provider not in ("claude", None):
        typer.echo(
            f"Warning: AI research only supports 'claude' provider (got '{provider}'). "
            "Falling back to Claude.",
            err=True,
        )

    return ClaudeTickerResearcher()


@screen_app.command("save-session")
def save_session(
    session_file: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to save session cookies (default: stockbit_session.json)"),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Seconds to wait for login completion", min=30),
    ] = 120,
) -> None:
    """
    Save a Stockbit browser session for autonomous pre-open screening.

    Opens a browser window (Chromium) for manual login. Once you are logged in,
    the session cookies are saved and used by subsequent 'saham screen pre-open' runs.

    Requires: pip install playwright && playwright install chromium

    Examples:
        saham screen save-session
        saham screen save-session --timeout 180
    """
    if not _playwright_available():
        typer.echo("Error: playwright not installed.", err=True)
        typer.echo("Run: pip install playwright && playwright install chromium", err=True)
        raise typer.Exit(1)

    from src.infrastructure.browser.playwright_stockbit import save_stockbit_session

    resolved = session_file or DEFAULT_SESSION_FILE
    try:
        save_stockbit_session(session_file=resolved, timeout=timeout)
    except Exception as e:
        typer.echo(f"Failed to save session: {e}", err=True)
        raise typer.Exit(1)
