"""
CLI: desk-centric view broker show | top-stocks | top-matrix | flow | history.

Supports --format table|json on every verb.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_contract_cli import (
    desk_envelope,
    echo_json,
    exit_missing_desk_data,
    resolve_output_format,
)
from src.adapters.cli.view_broker_desk_display import (
    display_desk_calendar,
    display_desk_flow,
    display_desk_history,
    display_desk_show,
    display_desk_top_matrix,
    display_desk_top_stocks,
)
from src.application.dto.view_ticker_contract import ViewWindow
from src.application.use_case.view_broker_desk_calendar_use_case import (
    ViewBrokerDeskCalendarRequest,
    ViewBrokerDeskCalendarUseCase,
)
from src.application.use_case.view_broker_desk_flow_use_case import (
    ViewBrokerDeskFlowRequest,
    ViewBrokerDeskFlowUseCase,
)
from src.application.use_case.view_broker_desk_history_use_case import (
    ViewBrokerDeskHistoryRequest,
    ViewBrokerDeskHistoryUseCase,
)
from src.application.use_case.view_broker_desk_show_use_case import (
    ViewBrokerDeskShowRequest,
    ViewBrokerDeskShowUseCase,
)
from src.application.use_case.view_broker_desk_top_matrix_use_case import (
    ViewBrokerDeskTopMatrixRequest,
    ViewBrokerDeskTopMatrixUseCase,
)
from src.application.use_case.view_broker_desk_top_stocks_use_case import (
    ViewBrokerDeskTopStocksRequest,
    ViewBrokerDeskTopStocksUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)

_FORMAT_OPT = Annotated[
    Optional[str],
    typer.Option("--format", help="Output format: table or json"),
]


def _repo_and_codes(db_path: Path | None):
    resolved = db_path or Path(load_app_config().storage.db_path)
    ia_cfg = load_institutional_accumulation_config()
    return SQLiteBrokerRepository(resolved), ia_cfg.foreign_broker_codes


def _desk_ticker_net_dict(row) -> dict:
    return {
        "ticker": row.ticker,
        "net_value": str(row.net_value),
        "net_lot": row.net_lot,
        "buy_value": str(row.buy_value),
        "sell_value": str(row.sell_value),
        "sessions": row.sessions,
    }


def _desk_day_net_dict(row) -> dict:
    return {
        "date": row.date.isoformat(),
        "net_value": str(row.net_value),
        "net_lot": row.net_lot,
        "buy_value": str(row.buy_value),
        "sell_value": str(row.sell_value),
        "ticker_count": row.ticker_count,
    }


def _daily_flow_dict(flow: BrokerDailyFlow) -> dict:
    return {
        "ticker": flow.ticker,
        "broker_code": flow.broker_code,
        "broker_name": flow.broker_name,
        "date": flow.date.isoformat(),
        "buy_lot": flow.buy_lot,
        "sell_lot": flow.sell_lot,
        "net_lot": flow.net_lot,
        "buy_value": str(flow.buy_value),
        "sell_value": str(flow.sell_value),
        "net_value": str(flow.net_value),
        "avg_buy_price": str(flow.avg_buy_price),
        "avg_sell_price": str(flow.avg_sell_price),
        "avg_price": str(flow.avg_price),
        "buy_pct": flow.buy_pct,
        "sell_pct": flow.sell_pct,
        "source": flow.source,
    }


def broker_desk_show(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: _FORMAT_OPT = None,
) -> None:
    """Show compact desk dashboard from tracked broker_daily_flow."""
    output_format = resolve_output_format(fmt or "table")
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskShowUseCase(repo, foreign_broker_codes=foreign).execute(
        ViewBrokerDeskShowRequest(broker_code=code)
    )
    if result is None:
        exit_missing_desk_data(code)

    if output_format == "json":
        echo_json(
            desk_envelope(
                code=result.broker_code,
                verb="show",
                as_of=result.as_of,
                scope_note=result.scope_note,
                data={
                    "broker_code": result.broker_code,
                    "broker_name": result.broker_name,
                    "broker_type": result.broker_type.value,
                    "as_of": result.as_of.isoformat(),
                    "day_net_value": str(result.day_net_value),
                    "day_net_lot": result.day_net_lot,
                    "day_ticker_count": result.day_ticker_count,
                    "top_buy_stocks": [_desk_ticker_net_dict(r) for r in result.top_buy_stocks],
                    "top_sell_stocks": [_desk_ticker_net_dict(r) for r in result.top_sell_stocks],
                },
            )
        )
        return

    display_desk_show(result)


def broker_desk_top_stocks(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    target_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date (YYYY-MM-DD), default: latest"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max stocks per side", min=1, max=50),
    ] = 20,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: _FORMAT_OPT = None,
) -> None:
    """Rank stocks for a tracked desk on one session (broker_daily_flow)."""
    output_format = resolve_output_format(fmt or "table")
    repo, foreign = _repo_and_codes(db_path)
    query_date = date.fromisoformat(target_date) if target_date else None
    result = ViewBrokerDeskTopStocksUseCase(repo, foreign_broker_codes=foreign).execute(
        ViewBrokerDeskTopStocksRequest(broker_code=code, target_date=query_date, limit=limit)
    )
    if result is None:
        exit_missing_desk_data(code)

    if output_format == "json":
        echo_json(
            desk_envelope(
                code=result.broker_code,
                verb="top-stocks",
                as_of=result.date,
                scope_note=result.scope_note,
                data={
                    "broker_code": result.broker_code,
                    "broker_name": result.broker_name,
                    "broker_type": result.broker_type.value,
                    "date": result.date.isoformat(),
                    "top_buy_stocks": [_desk_ticker_net_dict(r) for r in result.top_buy_stocks],
                    "top_sell_stocks": [_desk_ticker_net_dict(r) for r in result.top_sell_stocks],
                },
            )
        )
        return

    display_desk_top_stocks(result)


def broker_desk_top_matrix(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. YP)")],
    limit: Annotated[
        int,
        typer.Option("--limit", help="Top N per window", min=1, max=20),
    ] = 5,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: _FORMAT_OPT = None,
) -> None:
    """Top net-buy names by session window (1/3/5/10/20) with avg buy + streak."""
    output_format = resolve_output_format(fmt or "table")
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskTopMatrixUseCase(repo, foreign_broker_codes=foreign).execute(
        ViewBrokerDeskTopMatrixRequest(broker_code=code, limit=limit)
    )
    if result is None:
        exit_missing_desk_data(code)

    if output_format == "json":

        def _cell(c) -> dict:
            return {
                "ticker": c.ticker,
                "net_value": str(c.net_value),
                "window": c.window,
                "sessions_used": c.sessions_used,
                "avg_buy_price": str(c.avg_buy_price) if c.avg_buy_price is not None else None,
                "buy_streak": c.buy_streak,
                "is_partial": c.is_partial,
            }

        echo_json(
            desk_envelope(
                code=result.broker_code,
                verb="top-matrix",
                as_of=result.as_of,
                scope_note=result.scope_note,
                data={
                    "broker_code": result.broker_code,
                    "broker_name": result.broker_name,
                    "broker_type": result.broker_type.value,
                    "as_of": result.as_of.isoformat(),
                    "windows": list(result.windows),
                    "sessions_cached": result.sessions_cached,
                    "columns": {
                        str(w): [_cell(c) for c in (result.columns.get(w) or ())]
                        for w in result.windows
                    },
                    "top_ticker_1s": result.top_ticker_1s,
                },
            )
        )
        return

    display_desk_top_matrix(result)


def broker_desk_flow(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of trading days", min=1, max=365),
    ] = 10,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: _FORMAT_OPT = None,
) -> None:
    """Show desk aggregate net by day across cached tickers."""
    output_format = resolve_output_format(fmt or "table")
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskFlowUseCase(repo, foreign_broker_codes=foreign).execute(
        ViewBrokerDeskFlowRequest(broker_code=code, days=days)
    )
    if result is None:
        exit_missing_desk_data(code)

    if output_format == "json":
        day_rows = list(result.days)
        echo_json(
            desk_envelope(
                code=result.broker_code,
                verb="flow",
                as_of=day_rows[-1].date if day_rows else None,
                window=ViewWindow(days=days),
                scope_note=result.scope_note,
                data={
                    "broker_code": result.broker_code,
                    "broker_name": result.broker_name,
                    "broker_type": result.broker_type.value,
                    "days": [_desk_day_net_dict(d) for d in day_rows],
                },
            )
        )
        return

    display_desk_flow(result)


def broker_desk_calendar(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. YP)")],
    sessions: Annotated[
        int,
        typer.Option("--sessions", help="Max sessions (~month)", min=1, max=60),
    ] = 22,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: _FORMAT_OPT = None,
) -> None:
    """Session calendar: top stock · desk net · buy/sell (tracked desk only)."""
    output_format = resolve_output_format(fmt or "table")
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskCalendarUseCase(repo, foreign_broker_codes=foreign).execute(
        ViewBrokerDeskCalendarRequest(broker_code=code, max_sessions=sessions)
    )
    if result is None:
        exit_missing_desk_data(code)

    if output_format == "json":
        echo_json(
            desk_envelope(
                code=result.broker_code,
                verb="calendar",
                as_of=result.as_of,
                scope_note=result.scope_note,
                data={
                    "broker_code": result.broker_code,
                    "broker_name": result.broker_name,
                    "broker_type": result.broker_type.value,
                    "as_of": result.as_of.isoformat(),
                    "sessions_cached": result.sessions_cached,
                    "days": [
                        {
                            "date": d.date.isoformat(),
                            "net_value": str(d.net_value),
                            "buy_value": str(d.buy_value),
                            "sell_value": str(d.sell_value),
                            "top_ticker": d.top_ticker,
                            "top_net": str(d.top_net),
                            "ticker_count": d.ticker_count,
                        }
                        for d in result.days
                    ],
                },
            )
        )
        return

    display_desk_calendar(result)


def broker_desk_history(
    code: Annotated[str, typer.Argument(help="Broker desk code (e.g. AK)")],
    days: Annotated[
        int,
        typer.Option("--days", help="How many recent trading days", min=1, max=365),
    ] = 30,
    ticker: Annotated[
        Optional[str],
        typer.Option("--ticker", help="Pin to one stock ticker"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: _FORMAT_OPT = None,
) -> None:
    """Show desk per-ticker daily rows from broker_daily_flow."""
    output_format = resolve_output_format(fmt or "table")
    repo, foreign = _repo_and_codes(db_path)
    result = ViewBrokerDeskHistoryUseCase(repo, foreign_broker_codes=foreign).execute(
        ViewBrokerDeskHistoryRequest(broker_code=code, days=days, ticker=ticker)
    )
    if result is None:
        exit_missing_desk_data(code)

    if output_format == "json":
        flows = list(result.flows)
        echo_json(
            desk_envelope(
                code=result.broker_code,
                verb="history",
                as_of=flows[-1].date if flows else None,
                window=ViewWindow(days=days),
                scope_note=result.scope_note,
                data={
                    "broker_code": result.broker_code,
                    "broker_name": result.broker_name,
                    "broker_type": result.broker_type.value,
                    "pinned_ticker": result.pinned_ticker,
                    "flows": [_daily_flow_dict(f) for f in flows],
                },
            )
        )
        return

    display_desk_history(result)
