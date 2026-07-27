"""
CLI commands for strategy management.
Router and compatibility-only re-export module.

Layer: Adapter
"""

import typer

from src.adapters.cli.strategy_ai_create_commands import create
from src.adapters.cli.strategy_backtest_commands import backtest
from src.adapters.cli.strategy_lifecycle_commands import (
    init,
    list_strategies,
    validate,
)
from src.adapters.cli.strategy_skill_commands import skill_app

# Create Typer sub-app for strategy commands
strategy_app = typer.Typer(
    name="strategy",
    help=(
        "Manage strategy packages under strategies/ "
        "(init, validate, list, create, backtest, skill). "
        "Package YAML rule replay: `strategy backtest`. "
        "Swing setup portfolio sim: `saham backtest portfolio swing` "
        "(not this group)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
strategy_app.add_typer(skill_app, name="skill")

# Register imported commands explicitly
strategy_app.command("init")(init)
strategy_app.command("validate")(validate)
strategy_app.command("list")(list_strategies)
strategy_app.command("create")(create)
strategy_app.command("backtest")(backtest)

__all__ = [
    "strategy_app",
    "init",
    "validate",
    "list_strategies",
    "create",
    "backtest",
]
