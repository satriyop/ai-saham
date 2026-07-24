"""
CLI: view ticker top-brokers — top desks in a stock.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_contract_cli import (
    echo_json,
    exit_missing_ticker_data,
    resolve_output_format,
)
from src.adapters.cli.view_ticker_top_brokers_display import display_ticker_top_brokers
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    build_view_envelope,
    default_ticker_fetch_hint,
)
from src.application.use_case.view_ticker_top_brokers_use_case import (
    ViewTickerTopBrokersRequest,
    ViewTickerTopBrokersUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


def ticker_top_brokers(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    target_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date (YYYY-MM-DD), default: latest"),
    ] = None,
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
    Show top broker desks for a stock on a specific date.

    Prefers market top lists from broker_summaries. When those are empty
    (typical for IDX summaries), ranks tracked brokers from broker_daily_flow
    for the same date and labels the scope clearly.

    Examples:
        saham view ticker top-brokers BBCA
        saham view ticker top-brokers BBCA --date 2024-01-15
        saham view ticker top-brokers BBCA --format json
    """
    output_format = resolve_output_format(fmt or "table")
    db_path = db_path or Path(load_app_config().storage.db_path)
    repository = SQLiteBrokerRepository(db_path)
    ia_cfg = load_institutional_accumulation_config()
    use_case = ViewTickerTopBrokersUseCase(
        repository,
        foreign_broker_codes=ia_cfg.foreign_broker_codes,
    )

    query_date = date.fromisoformat(target_date) if target_date else None
    result = use_case.execute(
        ViewTickerTopBrokersRequest(ticker=ticker, target_date=query_date)
    )

    if result is None:
        exit_missing_ticker_data(
            ticker=ticker,
            what="top brokers",
            source="broker_summaries",
            fetch_hint=default_ticker_fetch_hint(ticker),
            for_date=target_date,
        )

    if output_format == "json":
        echo_json(
            build_view_envelope(
                subject_id=result.ticker,
                verb="top-brokers",
                status=ViewResultStatus.OK,
                as_of=result.date,
                source=result.tops_source,
                scope=result.tops_scope or "full",
                scope_note=result.tops_scope_note,
                fetch_hint=default_ticker_fetch_hint(result.ticker),
                data={
                    "summary": result.summary.to_dict(),
                    "top_buyers": [b.to_dict() for b in result.top_buyers],
                    "top_sellers": [s.to_dict() for s in result.top_sellers],
                    "tops_source": result.tops_source,
                    "tops_scope": result.tops_scope,
                },
            )
        )
        return

    display_ticker_top_brokers(
        result.ticker,
        result.summary,
        top_buyers=result.top_buyers,
        top_sellers=result.top_sellers,
        tops_scope_note=result.tops_scope_note,
    )
