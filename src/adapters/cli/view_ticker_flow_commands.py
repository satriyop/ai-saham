"""
CLI: view ticker flow — foreign flow summary table for a stock.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_contract_cli import (
    echo_json,
    exit_missing_ticker_data,
    resolve_output_format,
)
from src.adapters.cli.view_ticker_flow_table_display import display_ticker_flow_table
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewWindow,
    build_view_envelope,
)
from src.application.use_case.view_ticker_flow_use_case import ViewTickerFlowRequest
from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps
from src.infrastructure.config.app_config import load_app_config


def ticker_flow(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to show"),
    ] = 10,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Show foreign flow summary table for a stock (broker_summaries).

    Examples:
        saham view ticker flow BBCA --days 20
        saham view ticker flow BBCA --format json
    """
    cfg = load_app_config()
    db_path = db_path or Path(cfg.storage.db_path)
    output_format = resolve_output_format(fmt or cfg.analysis.format)

    deps = build_view_ticker_deps(db_path)
    result = deps.flow.execute(ViewTickerFlowRequest(ticker=ticker, days=days))

    if result is None:
        exit_missing_ticker_data(
            ticker=ticker,
            what="foreign flow summaries",
            source="broker_summaries",
            fetch_hint=f"saham fetch market {ticker.upper()}",
        )

    if output_format == "json":
        echo_json(
            build_view_envelope(
                subject_id=result.ticker,
                verb="flow",
                status=ViewResultStatus.OK,
                as_of=result.as_of,
                window=ViewWindow(
                    days=result.days,
                    from_date=result.summaries[0].date if result.summaries else None,
                    to_date=result.as_of,
                ),
                source=result.source,
                scope="full",
                fetch_hint=result.fetch_hint,
                data={
                    "total_net_value": str(result.total_net_value),
                    "buy_days": result.buy_days,
                    "sell_days": result.sell_days,
                    "summaries": [s.to_dict() for s in result.summaries],
                },
            )
        )
        return

    display_ticker_flow_table(result.ticker, list(result.summaries))
