"""
CLI adapter for stock analysis.

Entry point for the command-line interface.

Command groups:
  saham today      — read-only daily briefing
  saham fetch      — data ingestion lifecycle commands
  saham audit      — read-only audits (data-quality baseline manifest, source-field contracts)
  saham screen     — candidate discovery
  saham learn      — opening session journal (snapshot/track/grade)
  saham research   — research corpus and offline evaluation (may persist)
  saham view       — read-only local data browsing
  saham indicator  — technical indicators (compute, snapshot, create, list, show, delete)
  saham analyze    — live analysis (risk, compare, sentiment, audit, regime, chart, signal inspect)
  saham strategy   — strategy management (init, validate, list, create, backtest)
  saham trade      — paper trading workspace
  saham version    — version information

Layer: Adapter
"""

import typer

from src import __version__
from src.adapters.cli.analyze_commands import analyze_app
from src.adapters.cli.audit_commands import audit_app
from src.adapters.cli.fetch_commands import fetch_app
from src.adapters.cli.indicator_commands import indicator_app
from src.adapters.cli.learn_commands import learn_app
from src.adapters.cli.research_commands import research_app
from src.adapters.cli.screen_lifecycle_commands import screen_app
from src.adapters.cli.strategy_commands import strategy_app
from src.adapters.cli.today_commands import today
from src.adapters.cli.trade_commands import trade_app
from src.adapters.cli.view_commands import view_app

app = typer.Typer(
    name="saham",
    help="Local-first stock analysis CLI for Indonesia Stock Exchange (IDX)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# ── Command groups ─────────────────────────────────────────────────────────────

app.command("today")(today)
app.add_typer(fetch_app, name="fetch")
app.add_typer(audit_app, name="audit")
app.add_typer(screen_app, name="screen")
app.add_typer(learn_app, name="learn")
app.add_typer(research_app, name="research")
app.add_typer(view_app, name="view")
app.add_typer(indicator_app, name="indicator")
app.add_typer(analyze_app, name="analyze")
app.add_typer(strategy_app, name="strategy")
app.add_typer(trade_app, name="trade")


# ── Flat commands ──────────────────────────────────────────────────────────────

@app.command()
def version() -> None:
    """Show version and build information."""
    typer.echo(f"saham v{__version__}")
    typer.echo("Local-first stock analysis CLI for Indonesia Stock Exchange (IDX)")
    typer.echo("")
    typer.echo("For help:  saham --help")


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
