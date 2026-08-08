"""
Shared error/status display helpers for broker fetch CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from typing import Iterable, NoReturn

import typer

from src.adapters.cli.cli_errors import (
    CliErrorCategory,
    echo_cli_error,
    raise_data_unavailable,
    raise_internal_error,
    raise_user_error,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProviderError,
)


def echo_unknown_provider(provider_name: str, providers: Iterable[str]) -> None:
    echo_cli_error(
        f"Unknown provider: {provider_name}",
        category=CliErrorCategory.USER_INPUT,
    )
    typer.echo(f"Available providers: {', '.join(providers)}", err=True)


def exit_value_error(error: ValueError) -> NoReturn:
    raise_user_error(str(error))


def exit_broker_auth_error(error: BrokerDataAuthError) -> NoReturn:
    raise_data_unavailable(
        f"Auth error: {error}",
        tip="Run: saham fetch stockbit login",
    )


def exit_broker_provider_error(error: BrokerDataProviderError) -> NoReturn:
    raise_data_unavailable(str(error))


def exit_stockbit_provider_error(error: BrokerDataProviderError) -> NoReturn:
    if "Not authenticated" in str(error):
        raise_data_unavailable(
            "Not authenticated.",
            tip="Run: saham fetch stockbit login",
        )
    raise_data_unavailable(str(error))


def exit_unexpected_error(error: Exception) -> NoReturn:
    raise_internal_error(str(error))
