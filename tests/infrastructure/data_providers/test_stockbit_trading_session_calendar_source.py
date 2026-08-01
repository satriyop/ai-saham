"""Strict Stockbit calendar source parser tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.infrastructure.data_providers.stockbit_trading_session_calendar_source import (
    _PAGE_LIMIT,
    StockbitTradingSessionCalendarSource,
)

NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)


def _weekday_dates(n: int, start: date = date(2026, 7, 1)) -> list[str]:
    from datetime import timedelta

    out: list[str] = []
    cur = start
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


class _ScriptedClient:
    def __init__(self, pages: list[dict | Exception]):
        self._pages = list(pages)
        self.calls = 0

    def get(self, url: str):
        self.calls += 1
        if not self._pages:
            raise RuntimeError("no more pages")
        page = self._pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page


def _page(dates: list[str]) -> dict:
    return {"data": {"result": [{"date": d} for d in dates]}}


def test_single_page_under_limit() -> None:
    dates = _weekday_dates(49)
    src = StockbitTradingSessionCalendarSource(
        _ScriptedClient([_page(dates)]),
        captured_at=NOW,
    )
    snap = src.fetch_snapshot(date(2026, 7, 1), date(2026, 12, 31))
    assert len(snap.ordered_sessions) == 49
    assert src._api_client.calls == 1  # type: ignore[union-attr]


def test_exact_full_page_then_empty_completes() -> None:
    dates = _weekday_dates(50)
    client = _ScriptedClient([_page(dates), {"data": {"result": []}}])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    snap = src.fetch_snapshot(date(2026, 7, 1), date(2026, 12, 31))
    assert len(snap.ordered_sessions) == 50
    assert client.calls == 2


def test_fifty_one_rows_across_two_pages() -> None:
    first = _weekday_dates(50)
    second = _weekday_dates(1, start=date(2026, 9, 15))
    client = _ScriptedClient([_page(first), _page(second)])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    snap = src.fetch_snapshot(date(2026, 7, 1), date(2026, 12, 31))
    assert len(snap.ordered_sessions) == 51
    assert client.calls == 2


def test_network_error_on_page_two_fails_closed() -> None:
    first = _weekday_dates(50)
    client = _ScriptedClient([_page(first), RuntimeError("network")])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    with pytest.raises(LearningContractError, match="page 2 failed"):
        src.fetch_snapshot(date(2026, 7, 1), date(2026, 12, 31))


def test_missing_data_result_is_malformed() -> None:
    client = _ScriptedClient([{"data": {}}])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    with pytest.raises(LearningContractError, match="missing data.result"):
        src.fetch_snapshot(date(2026, 7, 1), date(2026, 7, 10))


def test_duplicate_within_page_rejected() -> None:
    client = _ScriptedClient(
        [{"data": {"result": [{"date": "2026-07-01"}, {"date": "2026-07-01"}]}}]
    )
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    with pytest.raises(LearningContractError, match="duplicate"):
        src.fetch_snapshot(date(2026, 7, 1), date(2026, 7, 10))


def test_duplicate_across_pages_rejected() -> None:
    first = _weekday_dates(50)
    # Force page 2 to repeat first date
    client = _ScriptedClient([_page(first), {"data": {"result": [{"date": first[0]}]}}])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    with pytest.raises(LearningContractError, match="duplicate"):
        src.fetch_snapshot(date(2026, 7, 1), date(2026, 12, 31))


def test_weekend_date_rejected() -> None:
    # 2026-07-04 is Saturday
    client = _ScriptedClient([{"data": {"result": [{"date": "2026-07-04"}]}}])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    with pytest.raises(LearningContractError, match="weekend"):
        src.fetch_snapshot(date(2026, 7, 1), date(2026, 7, 10))


def test_malformed_date_rejected() -> None:
    client = _ScriptedClient([{"data": {"result": [{"date": "not-a-date"}]}}])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    with pytest.raises(LearningContractError, match="malformed date"):
        src.fetch_snapshot(date(2026, 7, 1), date(2026, 7, 10))


def test_explicit_empty_result_is_valid_empty_snapshot() -> None:
    client = _ScriptedClient([{"data": {"result": []}}])
    src = StockbitTradingSessionCalendarSource(client, captured_at=NOW)
    snap = src.fetch_snapshot(date(2026, 7, 1), date(2026, 7, 10))
    assert snap.ordered_sessions == ()


def test_page_limit_constant() -> None:
    assert _PAGE_LIMIT == 50
