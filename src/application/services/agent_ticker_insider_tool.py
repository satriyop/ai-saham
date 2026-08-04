"""Bounded agent projection: recent insider (director/commissioner/major-holder)
buy/sell activity for a ticker (cache-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Protocol

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolFreshness,
    AgentToolName,
    AgentToolProvenance,
)
from src.domain.value_objects.insider_transaction import (
    InsiderTransaction,
    compute_net_buy_ratio,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_insider.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_insider.v1"

_DEFAULT_WINDOW_DAYS = 90
_MAX_WINDOW_DAYS = 90
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 20
_EVER_FETCHED_LOOKBACK_DAYS = 3650  # mirrors get_ticker_dashboard_use_case's 10y fallback

_INFO_NO_ACTIVITY_IN_WINDOW = "NO_INSIDER_ACTIVITY_IN_WINDOW"
_INFO_TRUNCATED_TO_LIMIT = "TRUNCATED_TO_LIMIT"


class _InsiderSource(Protocol):
    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "BUY",
        as_of_date: date | None = None,
    ) -> list[InsiderTransaction]: ...


@dataclass(frozen=True)
class TickerInsiderArguments(AgentToolArguments):
    ticker: str
    window_days: int
    limit: int

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.window_days < 1 or self.window_days > _MAX_WINDOW_DAYS:
            raise ValueError(f"window_days must be between 1 and {_MAX_WINDOW_DAYS}")
        if self.limit < 1 or self.limit > _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")


@dataclass(frozen=True)
class TickerInsiderTransactionData:
    name: str
    action_type: str
    shares: int
    price: float
    transaction_date: date


@dataclass(frozen=True)
class TickerInsiderResultData:
    schema_id: str
    ticker: str
    as_of: date | None
    window_days: int
    window_transaction_count: int
    transactions: tuple[TickerInsiderTransactionData, ...]
    buy_count: int
    sell_count: int
    net_shares: int
    net_buy_ratio: float | None


class TickerInsiderActivityTool:
    """Project recent cached insider buy/sell filings for one ticker."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_INSIDER_ACTIVITY,
        description=(
            "Return one ticker's recent cached insider (director/commissioner/major "
            "holder) buy/sell transactions and a bounded net buy/sell summary. "
            "Facts only — not a trade action or verdict."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "window_days",
                f"Optional lookback window in days (1-{_MAX_WINDOW_DAYS}). Empty "
                f"string defaults to {_DEFAULT_WINDOW_DAYS}.",
            ),
            AgentToolArgumentField(
                "limit",
                f"Optional max transactions returned (1-{_MAX_LIMIT}). Empty string "
                f"defaults to {_DEFAULT_LIMIT}.",
            ),
        ),
        required_context="LOCAL_TICKER_INSIDER_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(
        self,
        source: _InsiderSource,
        *,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._source = source
        self._today = today

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerInsiderArguments:
        if len(ordered_values) != 3:
            raise ValueError("ticker insider tool requires exactly three arguments")
        ticker = ordered_values[0].strip().upper()
        window_days = _parse_bounded_int(ordered_values[1], _DEFAULT_WINDOW_DAYS, _MAX_WINDOW_DAYS)
        limit = _parse_bounded_int(ordered_values[2], _DEFAULT_LIMIT, _MAX_LIMIT)
        return TickerInsiderArguments(ticker=ticker, window_days=window_days, limit=limit)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerInsiderArguments):
            raise TypeError("ticker insider tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-insider:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-insider-cache",
            source_reference=source_reference,
        )
        today = self._today()
        window_start = today - timedelta(days=arguments.window_days)
        try:
            # action_type="ALL" (not the port default "BUY") and an explicit
            # as_of_date make this call provably cache-only regardless of how the
            # injected source's api_client is wired elsewhere.
            window_txns = self._source.get_insider_transactions(
                ticker, window_start, today, "ALL", as_of_date=today
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_INSIDER_READ_FAILED",
                error_message="Ticker insider cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        newest_first = sorted(window_txns, key=lambda t: t.transaction_date, reverse=True)
        as_of = newest_first[0].transaction_date if newest_first else None
        warnings: list[str] = []

        if not newest_first:
            try:
                ever_fetched = bool(
                    self._source.get_insider_transactions(
                        ticker,
                        today - timedelta(days=_EVER_FETCHED_LOOKBACK_DAYS),
                        window_start - timedelta(days=1),
                        "ALL",
                        as_of_date=today,
                    )
                )
            except Exception:
                return AgentToolExecutionResult.create(
                    call_id=call_id,
                    name=self.definition.name,
                    status=AgentToolExecutionStatus.FAILED,
                    data=None,
                    error_code="TICKER_INSIDER_READ_FAILED",
                    error_message="Ticker insider cache could not be read",
                    provenance=provenance,
                    source_reference=source_reference,
                )
            if not ever_fetched:
                return AgentToolExecutionResult.create(
                    call_id=call_id,
                    name=self.definition.name,
                    status=AgentToolExecutionStatus.UNAVAILABLE,
                    data=None,
                    error_code="TICKER_INSIDER_UNAVAILABLE",
                    error_message="No cached insider activity for this ticker",
                    provenance=provenance,
                    source_reference=source_reference,
                )
            warnings.append(_INFO_NO_ACTIVITY_IN_WINDOW)

        window_count = len(newest_first)
        returned = newest_first[: arguments.limit]
        if len(returned) < window_count:
            warnings.append(_INFO_TRUNCATED_TO_LIMIT)

        buy_shares = sum(t.shares for t in newest_first if t.is_buy)
        sell_shares = sum(t.shares for t in newest_first if not t.is_buy)
        buy_count = sum(1 for t in newest_first if t.is_buy)
        sell_count = window_count - buy_count

        source_reference = f"ticker-insider:{ticker}:{as_of.isoformat() if as_of else 'none'}"
        provenance = AgentToolProvenance(
            source="ticker-insider-cache",
            as_of=as_of,
            source_reference=source_reference,
        )
        data = TickerInsiderResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=ticker,
            as_of=as_of,
            window_days=arguments.window_days,
            window_transaction_count=window_count,
            transactions=tuple(_row(t) for t in returned),
            buy_count=buy_count,
            sell_count=sell_count,
            net_shares=buy_shares - sell_shares,
            net_buy_ratio=compute_net_buy_ratio(newest_first),
        )
        warnings_tuple = tuple(warnings)
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=data,
            warnings=warnings_tuple,
            freshness=AgentToolFreshness(
                as_of=as_of,
                status=AgentToolExecutionStatus.SUCCESS.value,
                warnings=warnings_tuple,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _row(txn: InsiderTransaction) -> TickerInsiderTransactionData:
    return TickerInsiderTransactionData(
        name=txn.name,
        action_type=txn.action_type,
        shares=txn.shares,
        price=txn.price,
        transaction_date=txn.transaction_date,
    )


def _parse_bounded_int(raw: str, default: int, maximum: int) -> int:
    text = raw.strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("value must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"value must be between 1 and {maximum}")
    return min(value, maximum)
