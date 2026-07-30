"""
Router for Stockbit browser session management and adapter diagnostics CLI commands.

The actual command implementations live in per-command modules:
- fetch_stockbit_session_commands (login, reauth, status, browse)
- fetch_stockbit_spy_commands (spy)
- fetch_stockbit_diagnostic_commands (test, fetch-top5)

This module exists only to register commands on the stockbit_app router.

Layer: Adapter
"""

from __future__ import annotations

import typer

from src.adapters.cli.fetch_stockbit_diagnostic_commands import fetch_top5, test
from src.adapters.cli.fetch_stockbit_session_commands import browse, login, reauth, status
from src.adapters.cli.fetch_stockbit_spy_commands import spy

stockbit_app = typer.Typer(
    name="stockbit",
    help="Stockbit session management and adapter diagnostics",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

stockbit_app.command("login")(login)
stockbit_app.command("reauth")(reauth)
stockbit_app.command("status")(status)
stockbit_app.command("spy")(spy)
stockbit_app.command("test")(test)
stockbit_app.command("browse")(browse)
stockbit_app.command("fetch-top5")(fetch_top5)
