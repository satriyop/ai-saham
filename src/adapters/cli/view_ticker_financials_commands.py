"""
CLI: view ticker financials — multi-period statement deep-dive.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_contract_cli import (
    echo_json,
    resolve_output_format,
)
from src.adapters.cli.view_ticker_financials_display import display_ticker_financials
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewWindow,
    build_view_envelope,
)
from src.application.use_case.view_ticker_financials_use_case import (
    ViewTickerFinancialsRequest,
)
from src.domain.value_objects.company_financial_period import FinancialPeriodType
from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps
from src.infrastructure.config.app_config import load_app_config

_STATEMENT_CHOICES = ("income", "balance", "cashflow")
_PERIOD_CHOICES = ("quarterly", "annual")


def ticker_financials(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    statement: Annotated[
        str,
        typer.Option(
            "--statement",
            "-s",
            help="Statement kind: income (default), balance, cashflow",
        ),
    ] = "income",
    period: Annotated[
        str,
        typer.Option(
            "--period",
            "-p",
            help="Period grain: quarterly (default) or annual",
        ),
    ] = "quarterly",
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Max periods to show (newest first)", min=1, max=40),
    ] = 8,
    source: Annotated[
        Optional[str],
        typer.Option("--source", help="Filter by source (default: yahoo)"),
    ] = "yahoo",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """Show cached multi-period financial statements for a stock.

    Requires prior `saham fetch financials`. Supports income, balance sheet,
    and cash flow (yahoo-mapped metric subsets).

    Examples:
        saham view ticker financials BBCA
        saham view ticker financials BBCA --statement balance
        saham view ticker financials BBCA -s cashflow --period annual
        saham view ticker financials BBCA --format json
    """
    statement_key = statement.strip().lower()
    if statement_key not in _STATEMENT_CHOICES:
        typer.echo(
            f"Invalid --statement. Choose from: {', '.join(_STATEMENT_CHOICES)}",
            err=True,
        )
        raise typer.Exit(2)

    period_key = period.strip().lower()
    if period_key not in _PERIOD_CHOICES:
        typer.echo(
            f"Invalid --period. Choose from: {', '.join(_PERIOD_CHOICES)}",
            err=True,
        )
        raise typer.Exit(2)

    period_type: FinancialPeriodType = "quarter" if period_key == "quarterly" else "annual"
    output_format = resolve_output_format(fmt or "table")
    resolved_db = db_path or Path(load_app_config().storage.db_path)
    deps = build_view_ticker_deps(resolved_db)

    result = deps.financials.execute(
        ViewTickerFinancialsRequest(
            ticker=ticker,
            statement=statement_key,  # type: ignore[arg-type]
            period_type=period_type,
            limit=limit,
            source=source,
        )
    )

    if output_format == "json":
        status = ViewResultStatus.OK if result.status == "ok" else ViewResultStatus.EMPTY
        echo_json(
            build_view_envelope(
                subject_id=result.ticker,
                verb="financials",
                status=status,
                as_of=result.as_of,
                window=ViewWindow(
                    days=None,
                    from_date=result.periods[-1].period_end if result.periods else None,
                    to_date=result.as_of,
                ),
                source=result.source,
                scope=f"{result.statement}:{result.period_type}",
                scope_note=result.message,
                fetch_hint=result.fetch_hint,
                data={
                    "statement": result.statement,
                    "period_type": result.period_type,
                    "limit": limit,
                    "message": result.message,
                    "periods": [p.to_dict() for p in result.periods],
                },
            )
        )
        if result.status != "ok":
            raise typer.Exit(1)
        return

    display_ticker_financials(result)
    if result.status != "ok":
        raise typer.Exit(1)
