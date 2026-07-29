"""Semantic path spot-check: top-brokers use case + shared row formatter."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.shared.view_ticker_top_brokers_rows import format_ticker_top_brokers_rows
from src.application.use_case.view_ticker_top_brokers_use_case import (
    ViewTickerTopBrokersRequest,
    ViewTickerTopBrokersResult,
    ViewTickerTopBrokersUseCase,
)
from src.domain.entities.broker_flow import BrokerType


class _FakeRepo:
    def __init__(self, summary):
        self._summary = summary

    def get_broker_summaries(self, ticker, source=None):
        return [self._summary] if self._summary else []

    def get_broker_summary(self, ticker, target_date, source=None):
        return self._summary

    def get_broker_daily_flows(
        self,
        ticker,
        start_date=None,
        end_date=None,
        broker_codes=None,
        source=None,
    ):
        return []


def test_top_brokers_use_case_and_shared_rows_empty_tops_still_structured():
    summary = SimpleNamespace(
        ticker="BBCA",
        date=date(2026, 3, 1),
        top_buyers=(),
        top_sellers=(),
        foreign_net_value=Decimal("0"),
        foreign_flow_ratio=0.0,
        total_value=Decimal("0"),
    )
    uc = ViewTickerTopBrokersUseCase(_FakeRepo(summary), foreign_broker_codes=frozenset())
    result = uc.execute(ViewTickerTopBrokersRequest(ticker="BBCA", limit=10))
    assert isinstance(result, ViewTickerTopBrokersResult)
    assert result.ticker == "BBCA"
    assert result.date == date(2026, 3, 1)
    # empty tops → empty rows via shared formatter (same missing semantics path)
    rows = format_ticker_top_brokers_rows(result, limit=10)
    assert rows == []


def test_top_brokers_shared_rows_use_summary_net_when_no_pulse():
    buyer = SimpleNamespace(
        broker_code="ak",
        broker_name="Alpha",
        broker_type=BrokerType.FOREIGN,
        is_foreign=True,
        net_value=Decimal("1200000000"),
        net_lot=1,
    )
    summary = SimpleNamespace(
        ticker="BBCA",
        date=date(2026, 3, 1),
        top_buyers=(buyer,),
        top_sellers=(),
        foreign_net_value=Decimal("1"),
        foreign_flow_ratio=1.0,
        total_value=Decimal("1"),
    )
    result = ViewTickerTopBrokersResult(
        ticker="BBCA",
        date=date(2026, 3, 1),
        summary=summary,
        top_buyers=(buyer,),
        top_sellers=(),
        tops_source="summary",
        tops_scope=None,
        tops_scope_note=None,
    )
    rows = format_ticker_top_brokers_rows(result, limit=10)
    assert len(rows) == 1
    assert rows[0].code == "AK"
    assert rows[0].day_net == "1.20B"
    assert rows[0].net5 == "—"
