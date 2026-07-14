"""
Shared error/status display helpers for broker fetch CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from typing import Iterable, NoReturn

import typer

from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProviderError,
)


def echo_unknown_provider(provider_name: str, providers: Iterable[str]) -> None:
    typer.echo(
        typer.style(f"Unknown provider: {provider_name}", fg=typer.colors.RED)
    )
    typer.echo(f"Available providers: {', '.join(providers)}")


def exit_value_error(error: ValueError) -> NoReturn:
    typer.echo(typer.style(str(error), fg=typer.colors.RED))
    raise typer.Exit(1)


def exit_broker_auth_error(error: BrokerDataAuthError) -> NoReturn:
    typer.echo(typer.style(f"Auth error: {error}", fg=typer.colors.RED))
    typer.echo("Run: saham fetch stockbit login")
    raise typer.Exit(1)


def exit_broker_provider_error(error: BrokerDataProviderError) -> NoReturn:
    typer.echo(typer.style(f"Error: {error}", fg=typer.colors.RED))
    raise typer.Exit(1)


def exit_stockbit_provider_error(error: BrokerDataProviderError) -> NoReturn:
    if "Not authenticated" in str(error):
        typer.echo(
            typer.style("Not authenticated.", fg=typer.colors.RED)
            + " Run: saham fetch stockbit login"
        )
        raise typer.Exit(1)
    typer.echo(typer.style(f"Error: {error}", fg=typer.colors.RED), err=True)
    raise typer.Exit(1)


def exit_unexpected_error(error: Exception) -> NoReturn:
    typer.echo(typer.style(f"Error: {error}", fg=typer.colors.RED), err=True)
    raise typer.Exit(1)
