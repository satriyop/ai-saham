"""
CLI commands for pre-open market screening.

Usage patterns:

  # Autonomous (playwright + saved session):
  saham screen pre-open

  # Fast mode (no order book, ~15s):
  saham screen pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]' --fast

  # Normal mode with order book data:
  saham screen pre-open \\
    --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
    --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

  # Paper trade journal:
  saham screen log
  saham screen review --horizon 5

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
    help="Pre-open market screening and journal commands",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")
DEFAULT_STRATEGY_PATH = Path("strategies/pre-open-screener/strategy.yaml")
DEFAULT_SESSION_FILE = Path("stockbit_session.json")
DEFAULT_SIDECAR_PATH = Path("journals/.last-session.json")
DEFAULT_JOURNAL_PATH = Path("journals/pre-open.csv")


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _session_exists() -> bool:
    return DEFAULT_SESSION_FILE.exists()


def _load_config(strategy_path: Path, overrides: dict) -> PreOpenScreenConfig:
    if strategy_path.exists():
        with open(strategy_path) as f:
            data = yaml.safe_load(f)
        config = PreOpenScreenConfig.from_yaml(data)
    else:
        config = PreOpenScreenConfig()

    if overrides.get("iev_min") is not None:
        config.iev_min = overrides["iev_min"]
    if overrides.get("capital") is not None:
        config.capital = Decimal(str(overrides["capital"]))
    if overrides.get("stop_loss_pct") is not None:
        config.stop_loss_pct = Decimal(str(overrides["stop_loss_pct"]))
    if overrides.get("tick_above") is not None:
        config.tick_above = overrides["tick_above"]
    if overrides.get("top_n") is not None:
        config.top_n = overrides["top_n"]
    if overrides.get("fast_mode") is not None:
        config.fast_mode = overrides["fast_mode"]
    if overrides.get("max_gap") is not None:
        config.max_gap_pct = Decimal(str(overrides["max_gap"]))
    if overrides.get("atr_mult") is not None:
        config.atr_multiplier = Decimal(str(overrides["atr_mult"]))

    return config


def _print_browser_plan(config: PreOpenScreenConfig) -> None:
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
    top_label = f"top {config.top_n}" if config.top_n else "all rows"
    typer.echo(f"  3. Collect {top_label} with IEV >= {config.iev_min:,}")
    typer.echo("  4. Build JSON array:")
    typer.echo('     [{"ticker": "BBCA", "iev": 150000}, ...]')
    typer.echo("")
    if not config.fast_mode:
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
    else:
        typer.echo("STEP 2 — Re-run with movers data (fast mode — no order book needed)")
        typer.echo("-" * 40)
        typer.echo("  saham screen pre-open --fast --movers-json '<step1_json>'")
    typer.echo("")
    typer.echo("=" * 60)


def _display_results(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
) -> None:
    typer.echo("")
    typer.echo("=" * 90)
    typer.echo("PRE-OPEN SCREENER RESULTS")
    typer.echo("=" * 90)
    typer.echo(f"Date: {screened_date}   IEV filter: >= {iev_min:,}")
    typer.echo(f"Movers evaluated: {total_movers_seen}   Candidates: {len(candidates)}")
    typer.echo("")

    if not candidates:
        typer.echo("No candidates passed the IEV filter.")
        return

    header = (
        f"{'TICKER':<8} {'IEV':>8} {'GAP%':>7}  {'ENTRY-RANGE':>20}  "
        f"{'SUGGEST':>9}  {'ATR-STOP':>9}  {'STOP%':>6}  {'RSI':>5}  {'TREND':<8}"
    )
    typer.echo(header)
    typer.echo("-" * 90)

    for c in candidates:
        gap = c.gap_label
        rng = c.entry_range_label
        suggest = f"{c.entry_price:,.0f}" if c.entry_price else "—"
        stop = f"{c.stop_loss_price:,.0f}" if c.stop_loss_price else "—"
        stop_pct = c.risk_reward_label
        rsi_str = f"{float(c.rsi):.0f}" if c.rsi else "—"
        trend = c.trend_signal or "—"

        # Color trend
        if trend == "BULLISH":
            trend_str = typer.style(f"{trend:<8}", fg=typer.colors.GREEN)
        elif trend == "BEARISH":
            trend_str = typer.style(f"{trend:<8}", fg=typer.colors.RED)
        else:
            trend_str = typer.style(f"{trend:<8}", fg=typer.colors.YELLOW)

        typer.echo(
            f"{c.ticker:<8} {c.iev:>8,} {gap:>7}  {rng:>20}  "
            f"{suggest:>9}  {stop:>9}  {stop_pct:>6}  {rsi_str:>5}  {trend_str}"
        )

        # Show prev H/L as S/R context
        if c.prev_high and c.prev_low:
            hl = (
                typer.style(
                    f"  Prev H:{c.prev_high:,.0f}  L:{c.prev_low:,.0f}  "
                    f"(yesterday's intraday S/R levels)",
                    fg=typer.colors.BRIGHT_BLACK,
                )
            )
            typer.echo(hl)

    typer.echo("-" * 90)

    has_ai = any(c.ai_summary for c in candidates)
    if has_ai:
        typer.echo("")
        typer.echo("AI RESEARCH SUMMARIES")
        typer.echo("-" * 90)
        for c in candidates:
            if c.ai_summary:
                typer.echo(f"\n[{c.ticker}]")
                typer.echo(c.ai_summary)

    if warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for w in warnings:
            typer.echo(f"  ! {w}")

    typer.echo("")
    typer.echo("ENTRY-RANGE: enter at open IF opening price falls within this range")
    typer.echo("SUGGEST: limit order = prev_close + 0.5% (place after opening price known)")
    typer.echo("ATR-STOP: stop = entry - 1× ATR(14), capped at -7%")
    typer.echo("")
    typer.echo("DISCLAIMER: Analysis only. Not trading advice.")
    typer.echo("=" * 90)


def _write_sidecar(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    sidecar_path: Path,
) -> None:
    """Write session sidecar JSON so `saham screen log` can read it."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "screened_at": str(screened_date),
        "candidates": [
            {
                "ticker": c.ticker,
                "iev": c.iev,
                "gap_pct": str(c.gap_pct) if c.gap_pct is not None else None,
                "entry_range_low": str(c.entry_range_low) if c.entry_range_low else None,
                "entry_range_high": str(c.entry_range_high) if c.entry_range_high else None,
                "suggested_entry": str(c.entry_price) if c.entry_price else None,
                "atr_stop": str(c.stop_loss_price) if c.stop_loss_price else None,
                "trend": c.trend_signal,
                "rsi": str(c.rsi) if c.rsi else None,
            }
            for c in candidates
        ],
    }
    with open(sidecar_path, "w") as f:
        json.dump(data, f, indent=2)


@screen_app.command("pre-open")
def pre_open(
    movers_json: Annotated[
        Optional[str],
        typer.Option("--movers-json", help='Pre-fetched movers JSON array'),
    ] = None,
    order_books_json: Annotated[
        Optional[str],
        typer.Option("--order-books-json", help='Pre-fetched order books JSON object'),
    ] = None,
    iev_min: Annotated[Optional[int], typer.Option("--iev-min", min=1)] = None,
    capital: Annotated[Optional[int], typer.Option("--capital", min=1)] = None,
    stop_loss: Annotated[Optional[float], typer.Option("--stop-loss")] = None,
    tick_above: Annotated[Optional[int], typer.Option("--tick-above", min=1)] = None,
    top: Annotated[
        Optional[int],
        typer.Option("--top", help="Process only top N movers by IEV (default: from YAML)"),
    ] = None,
    fast: Annotated[
        bool,
        typer.Option("--fast/--no-fast", help="Skip order book fetches (~15s total)"),
    ] = False,
    max_gap: Annotated[
        Optional[float],
        typer.Option("--max-gap", help="Override max gap % threshold (e.g. 0.04 for 4%)"),
    ] = None,
    atr_mult: Annotated[
        Optional[float],
        typer.Option("--atr-mult", help="Override ATR stop multiplier (e.g. 1.5)"),
    ] = None,
    strategy_path: Annotated[
        Optional[Path],
        typer.Option("--strategy", "-s"),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    with_ai: Annotated[
        bool,
        typer.Option("--with-ai", help="Enable AI research (requires ANTHROPIC_API_KEY)"),
    ] = False,
    provider: Annotated[Optional[str], typer.Option("--provider")] = None,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless"),
    ] = True,
) -> None:
    """
    Run the pre-open market screener for IDX stocks.

    Outputs conditional entry ranges (not fixed prices) aligned to the IDX
    call auction mechanism. Enter at open only if opening price falls within
    the displayed range.

    Examples:
        # Fast mode (no order book, ~15s):
        saham screen pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]' --fast

        # Normal mode with order book:
        saham screen pre-open \\
          --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
          --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

        # Top 3 only, wider gap tolerance:
        saham screen pre-open --movers-json '...' --top 3 --max-gap 0.05

        # Log results after run:
        saham screen pre-open --movers-json '...' && saham screen log
    """
    resolved_strategy = strategy_path or DEFAULT_STRATEGY_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    overrides: dict = {
        "iev_min": iev_min,
        "capital": capital,
        "stop_loss_pct": stop_loss,
        "tick_above": tick_above,
        "top_n": top,
        "fast_mode": fast or None,
        "max_gap": max_gap,
        "atr_mult": atr_mult,
    }
    config = _load_config(resolved_strategy, overrides)

    if not movers_json:
        if _playwright_available() and _session_exists():
            typer.echo("Playwright session found — running autonomously...")
            from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider
            browser_provider = PlaywrightStockbitProvider(
                session_file=DEFAULT_SESSION_FILE,
                headless=headless,
            )
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

        top_label = f"top {config.top_n}" if config.top_n else str(len(movers_raw))
        mode_label = "fast" if config.fast_mode else "normal"
        typer.echo(
            f"Running pre-open screen ({top_label} movers, IEV >= {config.iev_min:,}, {mode_label} mode)..."
        )
        browser_provider = ManualBrowserDataProvider.from_json(movers_raw, order_books_raw)

    repository = SQLiteMarketRepository(db_path=resolved_db)
    registry = create_indicator_registry()

    ai_explainer = None
    if with_ai:
        try:
            ai_explainer = _build_ai_researcher(provider=provider)
        except Exception as e:
            typer.echo(f"Warning: Could not initialize AI research: {e}", err=True)

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

        # Write session sidecar for `saham screen log`
        _write_sidecar(result.candidates, result.screened_date, DEFAULT_SIDECAR_PATH)

    except BrowserInteractionRequired as e:
        typer.echo(f"\nBrowser action required:", err=True)
        typer.echo(f"  URL: {e.url}", err=True)
        typer.echo(f"  {e.instructions}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Screener failed: {e}", err=True)
        raise typer.Exit(1)


@screen_app.command("log")
def log_session(
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to session sidecar JSON (default: journals/.last-session.json)"),
    ] = None,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Path to journal CSV (default: journals/pre-open.csv)"),
    ] = None,
) -> None:
    """
    Append last screener run to the paper trade journal.

    Reads the session sidecar written by `saham screen pre-open` and
    appends one row per candidate to the journal CSV. Idempotent:
    re-running for the same date never duplicates rows.

    Example:
        saham screen pre-open --movers-json '...'
        saham screen log
        saham screen review --horizon 5
    """
    from src.application.services.paper_trade_journal import PaperTradeJournalService
    from src.domain.value_objects.screener_result import ScreenerCandidate
    from src.infrastructure.persistence.journal_csv_writer import JournalCsvWriter

    sidecar_path = session or DEFAULT_SIDECAR_PATH
    journal_path = journal or DEFAULT_JOURNAL_PATH

    if not sidecar_path.exists():
        typer.echo(
            f"No session sidecar found at '{sidecar_path}'.\n"
            "Run `saham screen pre-open` first.",
            err=True,
        )
        raise typer.Exit(1)

    with open(sidecar_path) as f:
        data = json.load(f)

    screened_at = date.fromisoformat(data["screened_at"])

    # Reconstruct minimal ScreenerCandidate objects for the journal service
    candidates = []
    for row in data["candidates"]:
        candidates.append(
            ScreenerCandidate(
                ticker=row["ticker"],
                iev=row["iev"],
                entry_price=Decimal(row["suggested_entry"]) if row.get("suggested_entry") else None,
                stop_loss_price=Decimal(row["atr_stop"]) if row.get("atr_stop") else None,
                capital=Decimal("0"),
                trend_signal=row.get("trend"),
                rsi=Decimal(row["rsi"]) if row.get("rsi") else None,
                gap_pct=Decimal(row["gap_pct"]) if row.get("gap_pct") else None,
                entry_range_low=Decimal(row["entry_range_low"]) if row.get("entry_range_low") else None,
                entry_range_high=Decimal(row["entry_range_high"]) if row.get("entry_range_high") else None,
            )
        )

    store = JournalCsvWriter(journal_path)
    repository = SQLiteMarketRepository(db_path=DEFAULT_DB_PATH)
    service = PaperTradeJournalService(store=store, repository=repository)

    count = service.log_session(candidates, screened_at)
    if count == 0:
        typer.echo(f"Already logged for {screened_at} — no new rows added ({journal_path})")
    else:
        typer.echo(f"Logged {count} candidate(s) for {screened_at} → {journal_path}")


@screen_app.command("review")
def review(
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Path to journal CSV"),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Trading days after screen date to check close price", min=1),
    ] = 5,
) -> None:
    """
    Review paper trade journal: hit-rate and direction accuracy.

    Fetches actual opening prices and N-day closes from the local database
    and computes what % of entry ranges were accurate.

    Example:
        saham screen review --horizon 5
    """
    from src.application.services.paper_trade_journal import PaperTradeJournalService
    from src.infrastructure.persistence.journal_csv_writer import JournalCsvWriter

    journal_path = journal or DEFAULT_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    if not journal_path.exists():
        typer.echo(
            f"No journal found at '{journal_path}'.\n"
            "Run `saham screen log` after a screening session first.",
            err=True,
        )
        raise typer.Exit(1)

    store = JournalCsvWriter(journal_path)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    service = PaperTradeJournalService(store=store, repository=repository)

    report = service.review(horizon_days=horizon)

    typer.echo("")
    typer.echo("=" * 55)
    typer.echo("PAPER TRADE JOURNAL REVIEW")
    typer.echo("=" * 55)
    typer.echo(f"Journal: {journal_path}")
    typer.echo(f"Total logged entries : {report.total_entries}")
    typer.echo(f"Entries with DB data : {report.entries_with_data}")

    if report.hit_rate_pct is not None:
        typer.echo(f"\nEntry range hit rate : {report.hit_rate_pct:.1f}%")
        typer.echo("  (% of sessions where opening price fell within entry range)")
    else:
        typer.echo("\nEntry range hit rate : N/A (no actual open prices yet)")

    if report.direction_accuracy_1d is not None:
        typer.echo(f"Direction accuracy 1d: {report.direction_accuracy_1d:.1f}%")
        typer.echo(f"Direction accuracy {horizon}d: {report.direction_accuracy_5d:.1f}%"
                   if report.direction_accuracy_5d else "")
    else:
        typer.echo("Direction accuracy   : N/A (need BULLISH calls + 1d close data)")

    if report.per_trend_breakdown:
        typer.echo("\nPer-trend breakdown:")
        typer.echo(f"  {'TREND':<10} {'TOTAL':>6} {'IN_RANGE':>9} {'UP_1D':>7}")
        typer.echo("  " + "-" * 35)
        for trend, stats in report.per_trend_breakdown.items():
            typer.echo(
                f"  {trend:<10} {stats['total']:>6} {stats['in_range']:>9} {stats['up_1d']:>7}"
            )

    typer.echo("")
    typer.echo("Note: hit-rate measures ENTRY RANGE accuracy, not trade profitability.")
    typer.echo("After 20+ sessions this becomes statistically meaningful.")
    typer.echo("=" * 55)


def _build_ai_researcher(provider: Optional[str] = None):
    from src.application.services.ai_research import ClaudeTickerResearcher
    if provider and provider not in ("claude", None):
        typer.echo(
            f"Warning: AI research only supports 'claude' provider. Falling back.",
            err=True,
        )
    return ClaudeTickerResearcher()


@screen_app.command("save-session")
def save_session(
    session_file: Annotated[
        Optional[Path],
        typer.Option("--session"),
    ] = None,
    timeout: Annotated[int, typer.Option("--timeout", min=30)] = 120,
) -> None:
    """
    Save a Stockbit browser session for autonomous pre-open screening.

    Requires: pip install playwright && playwright install chromium

    Example:
        saham screen save-session
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
