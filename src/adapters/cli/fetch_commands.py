"""
Lifecycle-oriented data ingestion commands.

Layer: Adapter
"""

import typer

from src.adapters.cli.fetch_audit_commands import data_quality_audit
from src.adapters.cli.fetch_broker_commands import (
    broker_fetch,
    broker_history,
    broker_import,
    broker_top_foreign,
)
from src.adapters.cli.fetch_iev_commands import collect_iev
from src.adapters.cli.fetch_market_commands import fetch_enrichment_history, fetch_market
from src.adapters.cli.fetch_status_commands import status
from src.adapters.cli.fetch_stockbit_commands import stockbit_app
from src.adapters.cli.fetch_universe_commands import universe_app

fetch_app = typer.Typer(
    name="fetch",
    help="Data ingestion — market data, broker flow, IEV, Stockbit, and universes.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

fetch_app.command("market")(fetch_market)
fetch_app.command("enrichment-history")(fetch_enrichment_history)
fetch_app.command("broker")(broker_fetch)
fetch_app.command("broker-import")(broker_import)
fetch_app.command("broker-history")(broker_history)
fetch_app.command("broker-top-foreign")(broker_top_foreign)
fetch_app.command("iev")(collect_iev)
fetch_app.command("status")(status)
fetch_app.command("audit")(data_quality_audit)
fetch_app.add_typer(stockbit_app, name="stockbit")
fetch_app.add_typer(universe_app, name="universe")
