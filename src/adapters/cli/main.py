"""
CLI adapter for stock analysis.

Entry point for the command-line interface.

Command groups:
  saham data       — market data (update, broker, stockbit, universe)
  saham indicator  — technical indicators (compute, snapshot, create, list, show, delete)
  saham analyze    — analysis and insights (risk, compare, sentiment, audit, regime, chart)
  saham strategy   — strategy management (init, validate, list, create, backtest)
  saham trade      — trading workflows (swing, intraday)
  saham skill      — skill documentation (generate, check, index)
  saham version    — version information

Layer: Adapter
"""

import typer

from src import __version__

app = typer.Typer(
    name="saham",
    help="Local-first stock analysis CLI for Indonesia Stock Exchange (IDX)",
    no_args_is_help=True,
)

# ── Command groups ─────────────────────────────────────────────────────────────

from src.adapters.cli.data_commands import data_app
from src.adapters.cli.indicator_commands import indicator_app
from src.adapters.cli.analyze_commands import analyze_app
from src.adapters.cli.strategy_commands import strategy_app
from src.adapters.cli.trade_commands import trade_app
from src.adapters.cli.skill_commands import skill_app

app.add_typer(data_app, name="data")
app.add_typer(indicator_app, name="indicator")
app.add_typer(analyze_app, name="analyze")
app.add_typer(strategy_app, name="strategy")
app.add_typer(trade_app, name="trade")
app.add_typer(skill_app, name="skill")


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
