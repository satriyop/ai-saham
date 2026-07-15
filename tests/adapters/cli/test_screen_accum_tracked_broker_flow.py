"""Pure tracked-broker-flow computation tests (application function, not CLI-specific).

Sourced from `broker_daily_flow` (tracked broker subset), not
`broker_summaries` (full-market top-broker rows) — these are different data
products and must not be conflated.
"""

from datetime import date
from decimal import Decimal

from src.application.services.tracked_broker_flow import compute_tracked_broker_flow_batch
from tests.application.use_case.accumulation_screen_fixtures import (
    MockBrokerRepositoryWithDaily,
    _daily_flow,
)


def test_screen_tracked_broker_flow_counts_local_noise_brokers():
    quality_batch = compute_tracked_broker_flow_batch(
        tickers=["BBCA"],
        broker_repo=MockBrokerRepositoryWithDaily(
            summaries=[],
            daily_flows=[
                _daily_flow("BBCA", date(2026, 6, 12), "YP", 1_000),
                _daily_flow("BBCA", date(2026, 6, 12), "XC", 650),
                _daily_flow("BBCA", date(2026, 6, 12), "AK", -200),
            ],
        ),
        smart_money_brokers=[],
        noise_brokers=["YP", "XC"],
        as_of_date=date(2026, 6, 12),
    )

    quality = quality_batch.get("BBCA")
    assert quality is not None
    assert quality.label == "noise+"
    assert quality.noise_flow == Decimal(1_000 * 100 * 1000) + Decimal(650 * 100 * 1000)
    assert quality.neutral_flow == Decimal(-200 * 100 * 1000)
    assert quality.to_dict()["source"] == "broker_daily_flow"
    assert quality.to_dict()["scope"] == "tracked_brokers"


def test_screen_tracked_broker_flow_marks_smart_selling_pressure():
    quality_batch = compute_tracked_broker_flow_batch(
        tickers=["BBCA"],
        broker_repo=MockBrokerRepositoryWithDaily(
            summaries=[],
            daily_flows=[
                _daily_flow("BBCA", date(2026, 6, 12), "CC", 350),
                _daily_flow("BBCA", date(2026, 6, 12), "BK", -850),
            ],
        ),
        smart_money_brokers=["BK"],
        noise_brokers=[],
        as_of_date=date(2026, 6, 12),
    )

    quality = quality_batch.get("BBCA")
    assert quality is not None
    assert quality.label == "smart-"
    assert quality.smart_flow == Decimal(-850 * 100 * 1000)


def test_screen_tracked_broker_flow_missing_rows_returns_none():
    """Missing tracked-broker rows must yield None, not a fabricated
    full-market label."""
    quality_batch = compute_tracked_broker_flow_batch(
        tickers=["BBCA"],
        broker_repo=MockBrokerRepositoryWithDaily(summaries=[], daily_flows=[]),
        smart_money_brokers=["BK"],
        noise_brokers=["YP"],
        as_of_date=date(2026, 6, 12),
    )

    assert quality_batch.get("BBCA") is None
