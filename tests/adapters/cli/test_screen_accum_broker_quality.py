"""Pure broker-quality computation tests (application function, not CLI-specific)."""

from datetime import date
from decimal import Decimal

from src.application.services.broker_quality import compute_broker_quality_batch
from src.domain.entities.broker_flow import BrokerType
from tests.adapters.cli.screen_accum_test_fixtures import (
    FakeBrokerSummaryRepository,
    _summary,
    _tx,
)


def test_screen_broker_quality_counts_local_noise_brokers():
    quality_batch = compute_broker_quality_batch(
        tickers=["BBCA"],
        broker_repo=FakeBrokerSummaryRepository([
            _summary(
                date(2026, 6, 12),
                top_buyers=(
                    _tx("YP", "100000000", "10000000", BrokerType.LOCAL),
                    _tx("XC", "70000000", "5000000", BrokerType.LOCAL),
                ),
                top_sellers=(_tx("AK", "5000000", "25000000"),),
            )
        ]),
        smart_money_brokers=[],
        noise_brokers=["YP", "XC"],
        as_of_date=date(2026, 6, 12),
    )

    quality = quality_batch.get("BBCA")
    assert quality is not None
    assert quality.label == "noise+"
    assert quality.noise_flow == Decimal("155000000")
    assert quality.neutral_flow == Decimal("-20000000")
    assert quality.to_dict()["source"] == "stockbit"


def test_screen_broker_quality_marks_smart_selling_pressure():
    quality_batch = compute_broker_quality_batch(
        tickers=["BBCA"],
        broker_repo=FakeBrokerSummaryRepository([
            _summary(
                date(2026, 6, 12),
                top_buyers=(_tx("CC", "40000000", "5000000"),),
                top_sellers=(_tx("BK", "5000000", "90000000"),),
            )
        ]),
        smart_money_brokers=["BK"],
        noise_brokers=[],
        as_of_date=date(2026, 6, 12),
    )

    quality = quality_batch.get("BBCA")
    assert quality is not None
    assert quality.label == "smart-"
    assert quality.smart_flow == Decimal("-85000000")
