"""
CLI commands for technical indicator operations.

Commands (all under `saham indicator`):
  saham indicator compute INDICATOR TICKER  — compute any indicator
  saham indicator snapshot TICKER           — multi-indicator view (SMA + EMA + RSI)
  saham indicator create INTENT             — create custom formula via AI
  saham indicator list                      — list all available indicators
  saham indicator show NAME                 — show saved formula details
  saham indicator delete NAME               — remove saved formula

Layer: Adapter
"""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.application.services.bootstrap import create_indicator_registry
from src.application.use_case.aggregate_indicators import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.application.use_case.create_indicator_from_intent import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentUseCase,
)
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter
from src.infrastructure.persistence.formula_storage import (
    FormulaStorage,
    FormulaStorageError,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

indicator_app = typer.Typer(
    name="indicator",
    help="Technical indicators — compute, snapshot, manage custom formulas.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

from src.infrastructure.config.app_config import APP_CFG

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_FORMULAS_PATH = Path("config/formulas.yaml")
DEFAULT_DAYS = APP_CFG.market.default_days
VALID_FIELDS = ["open", "high", "low", "close"]


def _validate_field(value: str) -> str:
    if value.lower() not in VALID_FIELDS:
        raise typer.BadParameter(
            f"Invalid field '{value}'. Must be one of: {', '.join(VALID_FIELDS)}"
        )
    return value.lower()


def _rsi_signal(value: Decimal) -> str:
    if value > Decimal("70"):
        return "OVERBOUGHT"
    if value < Decimal("30"):
        return "OVERSOLD"
    return "NEUTRAL"


def _no_data_error(ticker: str, days: int) -> None:
    typer.echo(f"[error] No cached data for {ticker.upper()}.", err=True)
    typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days {days}", err=True)


def _db_not_found_error(db_path: Path, ticker: str, days: int) -> None:
    typer.echo(f"[error] Database not found at {db_path}.", err=True)
    typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days {days}", err=True)


@indicator_app.command()
def compute(
    indicator: Annotated[str, typer.Argument(help="Indicator name (SMA, RSI, ATR, or custom formula)")],
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="Period (ignored for formula indicators)", min=1),
    ] = 14,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Days of history to load", min=1),
    ] = DEFAULT_DAYS,
    tail: Annotated[
        int,
        typer.Option("--tail", "-t", help="Show last N values (default 30)", min=1),
    ] = 30,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
    ] = None,
) -> None:
    """
    Compute any indicator values for a stock.

    Works with built-in indicators (SMA, EMA, RSI), plugins (ATR, VR, MFI…),
    and custom formulas created via `saham indicator create`.

    Examples:
        saham indicator compute RSI BBCA
        saham indicator compute SMA BBCA --period 50
        saham indicator compute SMOOTH_RSI BBCA --tail 10
        saham indicator compute ATR BBCA --days 180
    """
    registry = create_indicator_registry()
    indicator_upper = indicator.upper()
    ticker_upper = ticker.upper()

    if not registry.is_registered(indicator_upper):
        typer.echo(f"[error] Unknown indicator: {indicator_upper}", err=True)
        typer.echo("\nAvailable indicators:", err=True)
        for name in sorted(registry.list_indicators()):
            typer.echo(f"  {name}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    typer.echo(f"Loading {ticker_upper} · {indicator_upper} from {resolved_db}...")

    try:
        repository = SQLiteMarketRepository(db_path=resolved_db)
        candles = repository.get_candles(ticker_upper)

        if not candles:
            _no_data_error(ticker_upper, days)
            raise typer.Exit(1)

        if len(candles) > days:
            candles = candles[-days:]

        values = registry.compute(indicator_upper, candles, period)

        if not values:
            typer.echo(
                f"[error] Insufficient data for {indicator_upper}({period})."
                f" Have {len(candles)} candles.",
                err=True,
            )
            typer.echo(
                f"        Fix:   saham fetch market {ticker_upper} --days {days}", err=True
            )
            raise typer.Exit(1)

        display_values = values[-tail:] if len(values) > tail else values
        default_period = registry.get_default_period(indicator_upper)
        label = f"{indicator_upper}({period})" if default_period > 0 else indicator_upper

        # ── Header ────────────────────────────────────────────────────────────
        date_start, _ = values[0]
        _, date_end = values[-1]  # type: ignore[misc]
        date_end = display_values[-1][0]
        typer.echo(f"\n{'='*52}")
        typer.echo(f" {label}  ·  {ticker_upper}  ·  {values[0][0]} → {values[-1][0]}")
        typer.echo(f" {len(values)} values computed  (showing last {len(display_values)})")
        typer.echo(f"{'='*52}\n")

        # ── Table ─────────────────────────────────────────────────────────────
        is_rsi = indicator_upper == "RSI"
        if is_rsi:
            typer.echo(f"{'Date':<12} {label:>12}   Signal")
            typer.echo("─" * 36)
        else:
            typer.echo(f"{'Date':<12} {label:>14}")
            typer.echo("─" * 27)

        for dt, val in display_values:
            if is_rsi:
                sig = _rsi_signal(val)
                marker = f"  ← {sig}" if sig != "NEUTRAL" else ""
                typer.echo(f"{dt!s:<12} {val:>12.2f}{marker}")
            else:
                typer.echo(f"{dt!s:<12} {val:>14.2f}")

        # ── Summary ───────────────────────────────────────────────────────────
        all_vals = [v for _, v in values]
        all_dates = [d for d, _ in values]
        latest = all_vals[-1]
        peak_val = max(all_vals)
        trough_val = min(all_vals)
        peak_date = all_dates[all_vals.index(peak_val)]
        trough_date = all_dates[all_vals.index(trough_val)]

        typer.echo(f"\n{'─'*52}")
        typer.echo("Summary")
        typer.echo(f"{'─'*52}")
        if is_rsi:
            typer.echo(f"  Latest:   {latest:>10.2f}  ← {_rsi_signal(latest)}")
        else:
            typer.echo(f"  Latest:   {latest:>10.2f}")
        typer.echo(f"  Peak:     {peak_val:>10.2f}  ({peak_date})")
        typer.echo(f"  Trough:   {trough_val:>10.2f}  ({trough_date})")

    except typer.Exit:
        raise
    except FileNotFoundError:
        _db_not_found_error(resolved_db, ticker_upper, days)
        raise typer.Exit(1)
    except Exception as e:
        msg = str(e).lower()
        if "no such table" in msg or "no data" in msg:
            _no_data_error(ticker_upper, days)
        else:
            typer.echo(f"[error] Failed to compute {indicator_upper}: {e}", err=True)
        raise typer.Exit(1)


@indicator_app.command()
def snapshot(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    sma_period: Annotated[int, typer.Option("--sma", help="SMA period (default: 20)", min=1)] = 20,
    ema_period: Annotated[int, typer.Option("--ema", help="EMA period (default: 20)", min=1)] = 20,
    rsi_period: Annotated[int, typer.Option("--rsi", help="RSI period (default: 14)", min=1)] = 14,
    days: Annotated[int, typer.Option("--days", "-d", help="Days of history to load", min=1)] = DEFAULT_DAYS,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="Path to SQLite database")] = None,
    fmt: Annotated[str, typer.Option("--format", help="Output format: table or json")] = "table",
) -> None:
    """
    Multi-indicator view: SMA, EMA, and RSI aligned by date.

    Shows only dates where all three indicators have values.
    Requires cached data (run `saham fetch market TICKER` first).

    Examples:
        saham indicator snapshot BBCA
        saham indicator snapshot BBRI --sma 50 --ema 50
        saham indicator snapshot TLKM --rsi 7 --days 180
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    typer.echo(f"Loading {ticker_upper} · SMA({sma_period})/EMA({ema_period})/RSI({rsi_period}) from {resolved_db}...")

    try:
        repository = SQLiteMarketRepository(db_path=resolved_db)
        use_case = AggregateIndicatorsUseCase(repository=repository)
        response = use_case.execute(AggregateIndicatorsRequest(
            ticker=ticker,
            sma_period=sma_period,
            ema_period=ema_period,
            rsi_period=rsi_period,
            days=days,
        ))

        if not response.has_values:
            typer.echo(
                f"[error] Insufficient data for {ticker_upper}."
                f" Have {response.candle_count} candles,"
                f" need at least {max(sma_period, ema_period, rsi_period)}.",
                err=True,
            )
            typer.echo(f"        Fix:   saham fetch market {ticker_upper} --days {days}", err=True)
            raise typer.Exit(1)

        if fmt == "json":
            import json as _json
            out = [
                {
                    "date": str(s.date),
                    f"sma_{sma_period}": float(s.sma),
                    f"ema_{ema_period}": float(s.ema),
                    f"rsi_{rsi_period}": float(s.rsi),
                }
                for s in response.snapshots
            ]
            typer.echo(_json.dumps(out, indent=2))
            return

        # ── Header ────────────────────────────────────────────────────────────
        start, end = response.date_range or ("?", "?")
        typer.echo(f"\n{'='*60}")
        typer.echo(
            f" Indicator Snapshot  ·  {ticker_upper}  ·  {start} → {end}"
        )
        typer.echo(
            f" SMA({response.sma_period}) / EMA({response.ema_period}) / RSI({response.rsi_period})"
            f"  ·  {response.snapshot_count} rows"
        )
        typer.echo(f"{'='*60}\n")

        # ── Table ─────────────────────────────────────────────────────────────
        w = 13
        typer.echo(
            f"{'Date':<12} {'SMA':>{w}} {'EMA':>{w}} {'RSI':>8}   Signal"
        )
        typer.echo("─" * 60)

        for s in response.snapshots:
            sig = _rsi_signal(s.rsi)
            marker = f"  ← {sig}" if sig != "NEUTRAL" else ""
            typer.echo(
                f"{s.date!s:<12} {s.sma:>{w},.2f} {s.ema:>{w},.2f} {s.rsi:>8.2f}{marker}"
            )

        # ── Summary ───────────────────────────────────────────────────────────
        if response.snapshots:
            sma_vals = [s.sma for s in response.snapshots]
            ema_vals = [s.ema for s in response.snapshots]
            rsi_vals = [s.rsi for s in response.snapshots]
            latest = response.snapshots[-1]

            typer.echo(f"\n{'─'*60}")
            typer.echo("Summary (latest)")
            typer.echo(f"{'─'*60}")
            typer.echo(f"  SMA({response.sma_period}):  {latest.sma:>12,.2f}  Range [{min(sma_vals):,.2f} – {max(sma_vals):,.2f}]")
            typer.echo(f"  EMA({response.ema_period}):  {latest.ema:>12,.2f}  Range [{min(ema_vals):,.2f} – {max(ema_vals):,.2f}]")
            rsi_sig = _rsi_signal(latest.rsi)
            typer.echo(
                f"  RSI({response.rsi_period}):  {latest.rsi:>12.2f}  Range [{min(rsi_vals):.2f} – {max(rsi_vals):.2f}]"
                f"  ← {rsi_sig}"
            )

    except typer.Exit:
        raise
    except FileNotFoundError:
        _db_not_found_error(resolved_db, ticker_upper, days)
        raise typer.Exit(1)
    except Exception as e:
        msg = str(e).lower()
        if "no such table" in msg or "no data" in msg:
            _no_data_error(ticker_upper, days)
        else:
            typer.echo(f"[error] Failed to compute indicators: {e}", err=True)
        raise typer.Exit(1)


@indicator_app.command()
def create(
    intent: Annotated[str, typer.Argument(help="Natural language description of the indicator")],
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Indicator name (e.g., SMOOTH_RSI)")] = None,
    provider: Annotated[str, typer.Option("--provider", "-p", help="AI provider (deepseek/claude/openai/gemini/ollama/mock)")] = "mock",
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Model name for AI provider")] = None,
    save: Annotated[bool, typer.Option("--save/--no-save", help="Save formula to storage")] = True,
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas", help="Path to formulas file")] = None,
) -> None:
    """
    Create a custom indicator from natural language description.

    Uses AI to translate intent into a formula, validates it, and optionally saves
    it for reuse with `saham indicator compute`.

    AI Providers:
      mock      — local mock (no API key needed, for testing)
      claude    — Anthropic Claude (requires ANTHROPIC_API_KEY)
      openai    — OpenAI GPT (requires OPENAI_API_KEY)
      gemini    — Google Gemini (requires GOOGLE_API_KEY)
      ollama    — local Ollama (requires running Ollama server)

    Examples:
        saham indicator create "smoothed RSI with 14 period" --name SMOOTH_RSI
        saham indicator create "MACD line" --name MACD --provider claude
        saham indicator create "14-day RSI" --no-save
    """
    typer.echo(f"Translating: {intent!r}")
    typer.echo(f"Provider:    {provider}")

    try:
        registry = create_indicator_registry()
        available_functions = registry.get_available_indicators()
        translator = FormulaTranslatorAdapter(provider=provider, model=model)
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions=available_functions,
        )
        response = use_case.execute(CreateIndicatorFromIntentRequest(
            intent=intent,
            indicator_name=name,
        ))

        if response.unsupported:
            typer.echo("\n[error] This intent cannot be expressed as a formula.", err=True)
            typer.echo("        Tip:   Describe a mathematical combination of indicators.", err=True)
            raise typer.Exit(1)

        if not response.success:
            typer.echo(f"\n[error] {response.error_message}", err=True)
            raise typer.Exit(1)

        typer.echo(f"\nFormula: {response.formula}")

        indicator_name = name
        if not indicator_name:
            formula_clean = response.formula.replace("(", "_").replace(")", "")
            formula_clean = formula_clean.replace(",", "_").replace(" ", "")
            indicator_name = f"CUSTOM_{formula_clean[:20]}".upper()
            typer.echo(f"Auto-generated name: {indicator_name}")

        indicator_name = indicator_name.upper()

        if response.ast:
            try:
                registry.register_formula(indicator_name, response.ast)
                typer.echo(f"Registered: {indicator_name}")
            except Exception as e:
                typer.echo(f"Warning: Could not register formula in memory: {e}", err=True)

        if save and response.formula:
            resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
            storage = FormulaStorage(path=resolved_path)
            try:
                storage.save(name=indicator_name, formula=response.formula, intent=intent)
                typer.echo(f"Saved to:   {resolved_path}")
            except FormulaStorageError as e:
                typer.echo(f"Warning: Could not save formula: {e}", err=True)

        typer.echo(f"\nUse it: saham indicator compute {indicator_name} TICKER")

    except typer.Exit:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "api key" in msg or "authentication" in msg:
            typer.echo(f"[error] {e}", err=True)
            typer.echo(f"        Tip:   Set the API key environment variable for {provider}.", err=True)
        elif "connection" in msg or "timeout" in msg:
            typer.echo("[error] Could not connect to AI provider.", err=True)
            if provider == "ollama":
                typer.echo("        Tip:   Ensure Ollama is running: ollama serve", err=True)
            else:
                typer.echo("        Tip:   Check your internet connection.", err=True)
        else:
            typer.echo(f"[error] Failed to create indicator: {e}", err=True)
        raise typer.Exit(1)


@indicator_app.command(name="list")
def list_indicators(
    show_formulas: Annotated[bool, typer.Option("--formulas", "-f", help="Show formula expressions")] = False,
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas-file", help="Path to formulas file")] = None,
) -> None:
    """
    List all available indicators.

    Shows built-in indicators, loaded plugins, and saved custom formulas.
    Use --formulas to see the formula expressions for custom indicators.

    Examples:
        saham indicator list
        saham indicator list --formulas
    """
    from src.application.services.indicator_registry import BUILTIN_NAMES

    registry = create_indicator_registry()
    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)
    stored_formulas = storage.load_all()

    console = Console()

    console.print("")
    console.print("[bold]Built-in Indicators[/bold]")
    builtin_descriptions = {
        "SMA": "Simple Moving Average",
        "EMA": "Exponential Moving Average",
        "RSI": "Relative Strength Index",
    }

    builtin_table = Table(show_header=True, header_style="bold magenta")
    builtin_table.add_column("Indicator", style="cyan")
    builtin_table.add_column("Description", style="white")
    builtin_table.add_column("Default Period", justify="right")

    for ind_name in sorted(BUILTIN_NAMES):
        desc = builtin_descriptions.get(ind_name, "")
        period = registry.get_default_period(ind_name)
        builtin_table.add_row(ind_name, desc, str(period))
    console.print(builtin_table)

    plugin_names = set(registry.list_indicators()) - BUILTIN_NAMES - set(registry.list_formulas())
    if plugin_names:
        console.print("")
        console.print("[bold]Plugin Indicators[/bold]")
        plugin_table = Table(show_header=True, header_style="bold magenta")
        plugin_table.add_column("Indicator", style="cyan")
        plugin_table.add_column("Default Period", justify="right")
        for ind_name in sorted(plugin_names):
            period = registry.get_default_period(ind_name)
            plugin_table.add_row(ind_name, str(period))
        console.print(plugin_table)

    console.print("")
    console.print("[bold]Custom Formulas[/bold]")
    if stored_formulas:
        custom_table = Table(show_header=True, header_style="bold magenta")
        custom_table.add_column("Indicator", style="cyan")
        if show_formulas:
            custom_table.add_column("Formula Expression", style="green")

        for ind_name, stored in sorted(stored_formulas.items()):
            if show_formulas:
                custom_table.add_row(ind_name, stored.formula)
            else:
                custom_table.add_row(ind_name)
        console.print(custom_table)
        console.print(f"Formulas file: {resolved_path}")
    else:
        console.print("No custom formulas saved.")
        console.print("Tip: Use `saham indicator create` to create custom indicators.")

    total = len(registry.list_indicators()) + len(stored_formulas)
    console.print(f"\nTotal available: {total}")


@indicator_app.command()
def show(
    name: Annotated[str, typer.Argument(help="Formula name")],
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas-file", help="Path to formulas file")] = None,
) -> None:
    """
    Show details of a saved custom formula.

    Displays the formula expression, original intent, and creation date.

    Examples:
        saham indicator show SMOOTH_RSI
        saham indicator show MACD
    """
    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)
    stored = storage.get(name)

    if stored is None:
        typer.echo(f"[error] Formula '{name.upper()}' not found.", err=True)
        typer.echo("\nAvailable formulas:", err=True)
        for formula_name in storage.list_names():
            typer.echo(f"  {formula_name}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\nName:    {stored.name}")
    typer.echo(f"Formula: {stored.formula}")
    if stored.intent:
        typer.echo(f"Intent:  {stored.intent}")
    typer.echo(f"Created: {stored.created.strftime('%Y-%m-%d %H:%M:%S')}")


@indicator_app.command()
def delete(
    name: Annotated[str, typer.Argument(help="Formula name to delete")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt")] = False,
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas-file", help="Path to formulas file")] = None,
) -> None:
    """
    Delete a saved custom formula.

    Removes the formula from persistent storage. Built-in and plugin
    indicators cannot be deleted.

    Examples:
        saham indicator delete SMOOTH_RSI
        saham indicator delete MACD --force
    """
    from src.application.services.indicator_registry import BUILTIN_NAMES

    name_upper = name.upper()

    if name_upper in BUILTIN_NAMES:
        typer.echo(f"[error] Cannot delete built-in indicator: {name_upper}", err=True)
        raise typer.Exit(1)

    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)

    if not storage.exists(name_upper):
        typer.echo(f"[error] Formula '{name_upper}' not found in storage.", err=True)
        raise typer.Exit(1)

    if not force:
        stored = storage.get(name_upper)
        typer.echo("\nFormula to delete:")
        typer.echo(f"  Name:    {stored.name}")
        typer.echo(f"  Formula: {stored.formula}")
        confirm = typer.confirm("\nDelete this formula?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(0)

    try:
        deleted = storage.delete(name_upper)
        if deleted:
            typer.echo(f"Deleted {name_upper}.")
        else:
            typer.echo(f"[error] Formula '{name_upper}' not found.", err=True)
            raise typer.Exit(1)
    except FormulaStorageError as e:
        typer.echo(f"[error] Failed to delete formula: {e}", err=True)
        raise typer.Exit(1)
