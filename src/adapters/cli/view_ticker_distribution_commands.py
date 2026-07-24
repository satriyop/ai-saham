"""
CLI: view ticker distribution — cross-broker counterparty matrix for a stock.

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
from src.adapters.cli.view_ticker_distribution_display import (
    display_broker_distribution,
)
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    build_view_envelope,
)
from src.application.use_case.view_ticker_distribution_use_case import (
    ViewTickerDistributionRequest,
)
from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps
from src.infrastructure.config.app_config import load_app_config


def ticker_distribution(
    ticker: Annotated[str, typer.Argument(help="Ticker symbol (e.g. BBCA)")],
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Show cross-broker counterparty distribution for a ticker.

    Reveals which brokers bought FROM whom and sold TO whom today.

    Examples:
        saham view ticker distribution BBCA
        saham view ticker distribution GOTO --format json
    """
    cfg = load_app_config()
    db_path = db_path or Path(cfg.storage.db_path)
    output_format = resolve_output_format(fmt or "table")

    deps = build_view_ticker_deps(db_path)
    result = deps.distribution.execute(ViewTickerDistributionRequest(ticker=ticker))

    if result is None:
        exit_missing_ticker_data(
            ticker=ticker,
            what="broker distribution",
            source="broker_distribution_cache",
            fetch_hint=f"saham fetch market {ticker.upper()}",
        )

    if output_format == "json":
        snap = result.snapshot
        echo_json(
            build_view_envelope(
                subject_id=result.ticker,
                verb="distribution",
                status=ViewResultStatus.OK,
                as_of=result.as_of,
                source=result.source,
                scope="full",
                fetch_hint=result.fetch_hint,
                data={
                    "ticker": snap.ticker,
                    "date": snap.date.isoformat(),
                    "fetched_at": snap.fetched_at.isoformat() if snap.fetched_at else None,
                    "top_buyers": [
                        {
                            "broker_code": e.broker_code,
                            "broker_type": e.broker_type,
                            "amount_idr": e.amount_idr,
                            "counterparties": [
                                {
                                    "broker_code": c.broker_code,
                                    "broker_type": c.broker_type,
                                    "amount_idr": c.amount_idr,
                                }
                                for c in e.counterparties
                            ],
                        }
                        for e in snap.top_buyers
                    ],
                    "top_sellers": [
                        {
                            "broker_code": e.broker_code,
                            "broker_type": e.broker_type,
                            "amount_idr": e.amount_idr,
                            "counterparties": [
                                {
                                    "broker_code": c.broker_code,
                                    "broker_type": c.broker_type,
                                    "amount_idr": c.amount_idr,
                                }
                                for c in e.counterparties
                            ],
                        }
                        for e in snap.top_sellers
                    ],
                },
            )
        )
        return

    display_broker_distribution(result.snapshot)
