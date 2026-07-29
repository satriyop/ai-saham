"""
CLI adapter for stock analysis.

Entry point for the command-line interface.

Command groups:
  saham today      — read-only daily briefing
  saham fetch      — data ingestion lifecycle commands
  saham audit      — offline audits (data quality, sentiment accuracy)
  saham screen     — candidate discovery (live only)
  saham research   — research corpus / ML feeder (pre-open, accum)
  saham view       — read-only local data browsing
  saham indicator  — technical indicators (compute, snapshot, create, list, show, delete)
  saham inspect    — live diagnostic capability lenses (risk, sentiment, regime, signal accum)
  saham plan       — trade structure desk (plan swing → capital / SL / TP / lots)
  saham assess     — frozen-plan confirmation (assess pre-open)
  saham backtest   — offline historical sim (screen accum | portfolio swing)
  saham strategy   — strategy management (init, validate, list, create, backtest)
  saham policy     — guarded setup-config lifecycle (tune|review|validate|apply|status)
  saham trade      — paper trading notebook only (pre-open, accum)
  saham tui        — optional local terminal research workspace
  saham version    — version information

Layer: Adapter
"""

import typer

from src import __version__
from src.adapters.cli.assess_commands import assess_app
from src.adapters.cli.audit_commands import audit_app
from src.adapters.cli.backtest_commands import backtest_app
from src.adapters.cli.fetch_commands import fetch_app
from src.adapters.cli.indicator_commands import indicator_app
from src.adapters.cli.inspect_commands import inspect_app
from src.adapters.cli.plan_commands import plan_app
from src.adapters.cli.policy_commands import policy_app
from src.adapters.cli.research_commands import research_app
from src.adapters.cli.screen_lifecycle_commands import screen_app
from src.adapters.cli.strategy_commands import strategy_app
from src.adapters.cli.today_commands import today
from src.adapters.cli.trade_commands import trade_app
from src.adapters.cli.tui_commands import tui
from src.adapters.cli.view_commands import view_app

app = typer.Typer(
    name="saham",
    help="Local-first stock analysis CLI for Indonesia Stock Exchange (IDX)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# ── Command groups ─────────────────────────────────────────────────────────────
#
# Two grammars, git-style. Verb-first commands act on the *one* subject (market
# data and its analysis), like `git commit` / `git fetch`. Noun-first commands
# manage *collections* of named artifacts you author, like `git remote` /
# `git branch`. The help panels below make that split visible instead of showing
# one flat list — mirroring how `git help` groups commands into sections.

_PANEL_DATA = "Data"  # sync market data — git: collaborate (fetch/push)
_PANEL_ANALYSIS = "Analysis"  # transform the subject — git: grow history (commit/merge)
# Browse = local stored facts / offline health. Do not name this panel "Inspect"
# (that word is the live-lens verb `saham inspect` under Analysis).
_PANEL_BROWSE = "Browse"
_PANEL_ARTIFACTS = "Artifacts"  # manage named collections — git: remote/branch/tag
_PANEL_GENERAL = "General"  # meta / entry points

# Ordered in data-pipeline reading order: Data → Analysis → Browse → Artifacts
# → General. Note: Typer renders flat-command panels (today/tui/version) ahead of
# sub-group panels regardless of this order, so the on-screen panel sequence is
# only approximately this. The grouping — not the exact sequence — is the point.
app.add_typer(fetch_app, name="fetch", rich_help_panel=_PANEL_DATA)
app.command("today", rich_help_panel=_PANEL_ANALYSIS)(today)
app.add_typer(screen_app, name="screen", rich_help_panel=_PANEL_ANALYSIS)
app.add_typer(inspect_app, name="inspect", rich_help_panel=_PANEL_ANALYSIS)
app.add_typer(plan_app, name="plan", rich_help_panel=_PANEL_ANALYSIS)
app.add_typer(assess_app, name="assess", rich_help_panel=_PANEL_ANALYSIS)
app.add_typer(research_app, name="research", rich_help_panel=_PANEL_ANALYSIS)
app.add_typer(backtest_app, name="backtest", rich_help_panel=_PANEL_ANALYSIS)
app.add_typer(trade_app, name="trade", rich_help_panel=_PANEL_ANALYSIS)
app.add_typer(view_app, name="view", rich_help_panel=_PANEL_BROWSE)
app.add_typer(audit_app, name="audit", rich_help_panel=_PANEL_BROWSE)
app.add_typer(indicator_app, name="indicator", rich_help_panel=_PANEL_ARTIFACTS)
app.add_typer(strategy_app, name="strategy", rich_help_panel=_PANEL_ARTIFACTS)
app.add_typer(policy_app, name="policy", rich_help_panel=_PANEL_ARTIFACTS)
app.command("tui", rich_help_panel=_PANEL_GENERAL)(tui)


# ── Flat commands ──────────────────────────────────────────────────────────────


@app.command(rich_help_panel=_PANEL_GENERAL)
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
