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
from src.adapters.cli.view_ticker_financials_display import display_ticker_financials_many
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewWindow,
    build_view_envelope,
)
from src.application.use_case.view_ticker_financials_use_case import (
    ViewTickerFinancialsRequest,
    ViewTickerFinancialsResult,
)
from src.domain.value_objects.company_financial_period import (
    ALL_STATEMENT_KINDS,
    FinancialPeriodType,
    FinancialStatementKind,
)
from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps
from src.infrastructure.config.app_config import load_app_config

_STATEMENT_CHOICES = ("all", "income", "balance", "cashflow")
_PERIOD_CHOICES = ("quarterly", "annual")
_KIND_ORDER: tuple[FinancialStatementKind, ...] = ("income", "balance", "cashflow")


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
            help="Statement kind: all (default), income, balance, cashflow",
        ),
    ] = "all",
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

    Default shows income, balance, and cash flow panels. Filter with
    ``--statement income|balance|cashflow``. Requires prior
    ``saham fetch financials``.

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

    kinds = _resolve_kinds(statement_key)
    results: list[ViewTickerFinancialsResult] = []
    for kind in kinds:
        results.append(
            deps.financials.execute(
                ViewTickerFinancialsRequest(
                    ticker=ticker,
                    statement=kind,
                    period_type=period_type,
                    limit=limit,
                    source=source,
                )
            )
        )

    any_ok = any(r.status == "ok" for r in results)

    if output_format == "json":
        _echo_json(results, limit=limit, any_ok=any_ok)
        if not any_ok:
            raise typer.Exit(1)
        return

    display_ticker_financials_many(results)
    if not any_ok:
        raise typer.Exit(1)


def _resolve_kinds(statement_key: str) -> tuple[FinancialStatementKind, ...]:
    if statement_key == "all":
        return tuple(k for k in _KIND_ORDER if k in ALL_STATEMENT_KINDS)
    return (statement_key,)  # type: ignore[return-value]


def _echo_json(
    results: list[ViewTickerFinancialsResult],
    *,
    limit: int,
    any_ok: bool,
) -> None:
    primary = results[0]
    as_of_dates = [r.as_of for r in results if r.as_of is not None]
    as_of = max(as_of_dates) if as_of_dates else None
    from_dates = [r.periods[-1].period_end for r in results if r.periods]
    from_date = min(from_dates) if from_dates else None
    sources = {r.source for r in results if r.source}
    source = next(iter(sources)) if len(sources) == 1 else ("mixed" if sources else None)
    scope = (
        "all:" + primary.period_type
        if len(results) > 1
        else f"{primary.statement}:{primary.period_type}"
    )
    status = ViewResultStatus.OK if any_ok else ViewResultStatus.EMPTY
    messages = [r.message for r in results if r.message]
    echo_json(
        build_view_envelope(
            subject_id=primary.ticker,
            verb="financials",
            status=status,
            as_of=as_of,
            window=ViewWindow(
                days=None,
                from_date=from_date,
                to_date=as_of,
            ),
            source=source,
            scope=scope,
            scope_note="; ".join(messages) if messages and not any_ok else None,
            fetch_hint=primary.fetch_hint,
            data={
                "period_type": primary.period_type,
                "limit": limit,
                "statements": [
                    {
                        "statement": r.statement,
                        "status": r.status,
                        "source": r.source,
                        "message": r.message,
                        "periods": [p.to_dict() for p in r.periods],
                    }
                    for r in results
                ],
            },
        )
    )
