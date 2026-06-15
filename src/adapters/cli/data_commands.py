"""
CLI commands for market data acquisition.

Commands (all under `saham data`):
  saham data update [TICKERS]   — fetch candles + broker flow
  saham data broker …           — broker flow management (sub-group)
  saham data stockbit …         — Stockbit session management (sub-group)
  saham data universe …         — stock universe lists (sub-group)

Layer: Adapter
"""

import typer

from src.adapters.cli.update_commands import update
from src.adapters.cli.broker_commands import broker_app
from src.adapters.cli.stockbit_commands import stockbit_app
from src.adapters.cli.accumulation_commands import universe_app

data_app = typer.Typer(
    name="data",
    help="Market data — fetch candles, broker flow, and universe lists.",
    no_args_is_help=True,
)

data_app.command("update")(update)
data_app.add_typer(broker_app, name="broker")
data_app.add_typer(stockbit_app, name="stockbit")
data_app.add_typer(universe_app, name="universe")
