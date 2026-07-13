"""Shared fixtures and helpers for accumulation screen CLI tests."""

from datetime import date
from decimal import Decimal

from typer.testing import CliRunner

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
)
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType

runner = CliRunner()


def _tx(
    code: str,
    buy: str,
    sell: str,
    broker_type: BrokerType = BrokerType.FOREIGN,
) -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
        broker_type=broker_type,
        buy_lot=1000,
        sell_lot=500,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _summary(
    day: date,
    top_buyers: tuple[BrokerTransaction, ...] = (),
    top_sellers: tuple[BrokerTransaction, ...] = (),
) -> BrokerSummary:
    return BrokerSummary(
        ticker="BBCA",
        date=day,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=Decimal("1000"),
        foreign_sell_value=Decimal("500"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("10000"),
        total_lot=100,
        source="stockbit",
    )


def _candidate(**overrides) -> AccumulationCandidate:
    values = {
        "ticker": "BBCA",
        "window_days": 7,
        "net_buy_days": 5,
        "total_days": 7,
        "net_buy_ratio": 5 / 7,
        "total_net_value": Decimal("10000000000"),
        "consecutive_streak": 3,
        "foreign_vwap": Decimal("1030"),
        "current_price": Decimal("1000"),
        "vwap_discount_pct": 3.0,
        "rsi": 55.0,
        "trend": "SIDE",
        "foreign_flow_score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


class FakeBrokerSummaryRepository:
    def __init__(self, summaries):
        self._summaries = summaries

    def get_broker_summaries(self, ticker: str, start_date=None, end_date=None):
        return [
            summary
            for summary in self._summaries
            if summary.ticker == ticker
            and (start_date is None or summary.date >= start_date)
            and (end_date is None or summary.date <= end_date)
        ]


def _fake_workflow_result(**overrides):
    """Build a RunAccumulationScreenWorkflowResult-like object for CLI mocks."""
    from src.application.use_case.run_accumulation_screen_workflow_use_case import (
        RunAccumulationScreenWorkflowResult,
    )
    params = dict(
        response=None,
        multi_results={},
        broker_quality={},
        strategy_signals={},
        save_result=None,
        warnings=(),
    )
    params.update(overrides)
    return RunAccumulationScreenWorkflowResult(**params)
