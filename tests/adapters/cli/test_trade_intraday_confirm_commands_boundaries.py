"""
Boundary tests for trade_intraday_confirm_commands.py.

Ensures confirm_open() stays a thin Typer adapter: concrete Stockbit
provider/session/config wiring must only happen through
trade_intraday_confirm_factory.py, never directly in the command module.

Layer: Adapter (test)
"""

from pathlib import Path

_MODULE_PATH = Path("src/adapters/cli/trade_intraday_confirm_commands.py")

_FORBIDDEN_SYMBOLS = (
    "load_intraday_confirmation_candidates",
    "load_intraday_confirmation_tickers",
    "load_opening_prices_from_track_file",
    "load_pre_open_market_regime",
    "write_intraday_confirmation_sidecar",
    "ConfirmIntradayOpenUseCase",
    "ResolveOpeningPricesUseCase",
    "StockbitOrderBookProvider",
    "StockbitRunningTradeProvider",
    "get_stockbit_session",
    "load_pre_open_screen_config",
)


def test_command_module_does_not_reference_workflow_internals():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    for symbol in _FORBIDDEN_SYMBOLS:
        assert symbol not in source, (
            f"trade_intraday_confirm_commands.py references workflow-owned symbol: {symbol}"
        )
