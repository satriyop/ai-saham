"""Strict Stockbit IHSG historical probe for trading-session calendar snapshots.

Unlike StockbitHistoricalProvider (tolerant market-data fallback that may return
partial pages after errors), this source fails closed: every page must succeed
and the complete range must validate before a snapshot is produced. Writes nothing.

Pagination (no total metadata in Stockbit historical summary responses):
- page with fewer than 50 rows → complete
- page with exactly 50 rows → fetch next page
- next page with explicit result=[] → complete
- missing/malformed body or network failure → fail

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
    validate_active_stockbit_calendar_snapshot,
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
        captured_at: datetime | None = None,
    ) -> None:
        self._api_client = api_client
        self._stockbit_config = stockbit_config or load_stockbit_config()
        self._source_revision = source_revision
        self._benchmark = benchmark
        self._captured_at = captured_at

    def fetch_snapshot(
        self,
        coverage_start: date,
        coverage_end: date,
    ) -> TradingSessionCalendarSnapshot:
        if coverage_start > coverage_end:
            raise LearningContractError("coverage_start must not be after coverage_end")
        if self._api_client is None:
            raise LearningContractError("Stockbit API client unavailable for calendar snapshot")
        if self._benchmark != TRADING_SESSION_CALENDAR_BENCHMARK_IHSG:
            raise LearningContractError(
                f"strict calendar source only supports IHSG, got {self._benchmark!r}"
            )

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
                # Explicit empty result: complete for page 1 (empty range) or
                # after a full page (exact-50 termination).
                break
            for row in rows:
                session_dates.append(_parse_session_date(row, page=page))
            if len(rows) < _PAGE_LIMIT:
                break
            page += 1

        if len(session_dates) != len(set(session_dates)):
            raise LearningContractError("Stockbit calendar contains duplicate session dates")
        ordered = tuple(sorted(session_dates))
        captured = self._captured_at or datetime.now(timezone.utc)
        snapshot = TradingSessionCalendarSnapshot.create(
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            ordered_sessions=ordered,
            source_revision=self._source_revision,
            captured_at=captured,
            contract_id=STOCKBIT_TRADING_SESSIONS_CONTRACT,
            source=TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT,
            benchmark=TRADING_SESSION_CALENDAR_BENCHMARK_IHSG,
        )
        validate_active_stockbit_calendar_snapshot(snapshot)
        return snapshot


def _extract_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if not isinstance(data, dict):
        raise LearningContractError("strict Stockbit calendar: data is not an object")
    if "result" not in data:
        raise LearningContractError("Stockbit response missing data.result")
    rows = data["result"]
    if not isinstance(rows, list):
        raise LearningContractError("Stockbit data.result must be a list")
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
        text = str(raw).strip()
        if "T" in text:
            text = text.split("T", 1)[0]
        session = date.fromisoformat(text[:10])
    except (TypeError, ValueError) as exc:
        raise LearningContractError(
            f"strict Stockbit calendar page {page}: malformed date {raw!r}"
        ) from exc
    return session
