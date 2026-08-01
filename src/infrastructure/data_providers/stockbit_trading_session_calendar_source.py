"""Strict Stockbit IHSG historical probe for trading-session calendar snapshots.

Unlike StockbitHistoricalProvider (tolerant market-data fallback that may return
partial pages after errors), this source fails closed: every page must succeed
and the complete range must validate before a snapshot is produced. Writes nothing.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.trading_session_calendar_snapshot import (
    STOCKBIT_TRADING_SESSIONS_CONTRACT,
    TRADING_SESSION_CALENDAR_BENCHMARK_IHSG,
    TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT,
    TradingSessionCalendarSnapshot,
)
from src.infrastructure.config.stockbit_config import StockbitConfig, load_stockbit_config

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

_PAGE_LIMIT = 50
_DEFAULT_SOURCE_REVISION = "stockbit.exodus.historical_summary.v1"


class StockbitTradingSessionCalendarSource:
    """Strict TradingSessionCalendarSource for IHSG historical sessions."""

    def __init__(
        self,
        api_client: StockbitApiClient | None,
        *,
        stockbit_config: StockbitConfig | None = None,
        source_revision: str = _DEFAULT_SOURCE_REVISION,
        benchmark: str = TRADING_SESSION_CALENDAR_BENCHMARK_IHSG,
    ) -> None:
        self._api_client = api_client
        self._stockbit_config = stockbit_config or load_stockbit_config()
        self._source_revision = source_revision
        self._benchmark = benchmark

    def fetch_snapshot(
        self,
        coverage_start: date,
        coverage_end: date,
    ) -> TradingSessionCalendarSnapshot:
        if coverage_start > coverage_end:
            raise LearningContractError("coverage_start must not be after coverage_end")
        if self._api_client is None:
            raise LearningContractError("Stockbit API client unavailable for calendar snapshot")

        base_url = self._stockbit_config.historical_summary_url.format(ticker=self._benchmark)
        session_dates: list[date] = []
        page = 1
        while True:
            url = (
                f"{base_url}"
                f"?period=HS_PERIOD_DAILY"
                f"&start_date={coverage_start.isoformat()}"
                f"&end_date={coverage_end.isoformat()}"
                f"&limit={_PAGE_LIMIT}&page={page}"
            )
            try:
                body = self._api_client.get(url)
            except Exception as exc:
                raise LearningContractError(
                    f"strict Stockbit calendar page {page} failed: {exc}"
                ) from exc
            if not isinstance(body, dict) or not body:
                raise LearningContractError(
                    f"strict Stockbit calendar page {page} returned empty/malformed body"
                )
            rows = _extract_rows(body)
            if not rows:
                if page == 1:
                    # Empty complete range is valid (no sessions in window).
                    break
                raise LearningContractError(
                    f"strict Stockbit calendar page {page} returned no rows mid-pagination"
                )
            for row in rows:
                session_dates.append(_parse_session_date(row, page=page))
            if len(rows) < _PAGE_LIMIT:
                break
            page += 1

        # Reject duplicates / out of range / weekends via create validators.
        unique_sorted = tuple(sorted(set(session_dates)))
        return TradingSessionCalendarSnapshot.create(
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            ordered_sessions=unique_sorted,
            source_revision=self._source_revision,
            captured_at=datetime.now(timezone.utc),
            contract_id=STOCKBIT_TRADING_SESSIONS_CONTRACT,
            source=TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT,
            benchmark=self._benchmark,
        )


def _extract_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if not isinstance(data, dict):
        raise LearningContractError("strict Stockbit calendar: data is not an object")
    rows = data.get("result")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise LearningContractError("strict Stockbit calendar: result is not a list")
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise LearningContractError(f"strict Stockbit calendar: result[{i}] is not an object")
        out.append(row)
    return out


def _parse_session_date(row: dict[str, Any], *, page: int) -> date:
    raw = row.get("date")
    if raw is None:
        raise LearningContractError(f"strict Stockbit calendar page {page}: row missing date")
    try:
        # Accept YYYY-MM-DD or epoch-like strings used by other parsers.
        text = str(raw).strip()
        if "T" in text:
            text = text.split("T", 1)[0]
        session = date.fromisoformat(text[:10])
    except (TypeError, ValueError) as exc:
        raise LearningContractError(
            f"strict Stockbit calendar page {page}: malformed date {raw!r}"
        ) from exc
    return session
