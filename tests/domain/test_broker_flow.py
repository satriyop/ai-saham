"""Tests for broker flow entities."""

from datetime import date
from decimal import Decimal

import pytest

from src.domain.entities.broker_flow import (
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
)


class TestBrokerTransaction:
    """Tests for BrokerTransaction entity."""

    def test_create_valid_transaction(self):
        """Should create a valid broker transaction."""
        tx = BrokerTransaction(
            broker_code="YP",
            broker_name="Mirae Asset Sekuritas",
            broker_type=BrokerType.FOREIGN,
            buy_lot=1000,
            sell_lot=500,
            buy_value=Decimal("10000000000"),  # 10B
            sell_value=Decimal("5000000000"),  # 5B
            avg_buy_price=Decimal("10000"),
            avg_sell_price=Decimal("10000"),
        )

        assert tx.broker_code == "YP"
        assert tx.broker_type == BrokerType.FOREIGN
        assert tx.net_lot == 500
        assert tx.net_value == Decimal("5000000000")
        assert tx.is_net_buyer is True
        assert tx.is_net_seller is False
        assert tx.is_foreign is True

    def test_net_seller(self):
        """Should correctly identify net seller."""
        tx = BrokerTransaction(
            broker_code="CC",
            broker_name="Mandiri Sekuritas",
            broker_type=BrokerType.LOCAL,
            buy_lot=500,
            sell_lot=1000,
            buy_value=Decimal("5000000000"),
            sell_value=Decimal("10000000000"),
            avg_buy_price=Decimal("10000"),
            avg_sell_price=Decimal("10000"),
        )

        assert tx.net_lot == -500
        assert tx.net_value == Decimal("-5000000000")
        assert tx.is_net_buyer is False
        assert tx.is_net_seller is True
        assert tx.is_foreign is False

    def test_empty_broker_code_raises(self):
        """Should raise for empty broker code."""
        with pytest.raises(ValueError, match="Broker code cannot be empty"):
            BrokerTransaction(
                broker_code="",
                broker_name="Test",
                broker_type=BrokerType.LOCAL,
                buy_lot=0,
                sell_lot=0,
                buy_value=Decimal("0"),
                sell_value=Decimal("0"),
                avg_buy_price=Decimal("0"),
                avg_sell_price=Decimal("0"),
            )

    def test_negative_lot_raises(self):
        """Should raise for negative lot counts."""
        with pytest.raises(ValueError, match="cannot be negative"):
            BrokerTransaction(
                broker_code="YP",
                broker_name="Test",
                broker_type=BrokerType.LOCAL,
                buy_lot=-100,
                sell_lot=0,
                buy_value=Decimal("0"),
                sell_value=Decimal("0"),
                avg_buy_price=Decimal("0"),
                avg_sell_price=Decimal("0"),
            )

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        tx = BrokerTransaction(
            broker_code="MS",
            broker_name="Morgan Stanley",
            broker_type=BrokerType.FOREIGN,
            buy_lot=2000,
            sell_lot=1000,
            buy_value=Decimal("20000000000"),
            sell_value=Decimal("10000000000"),
            avg_buy_price=Decimal("10000"),
            avg_sell_price=Decimal("10000"),
        )

        data = tx.to_dict()
        restored = BrokerTransaction.from_dict(data)

        assert restored == tx


class TestBrokerSummary:
    """Tests for BrokerSummary entity."""

    def test_create_valid_summary(self):
        """Should create a valid broker summary."""
        buyer = BrokerTransaction(
            broker_code="YP",
            broker_name="Mirae",
            broker_type=BrokerType.FOREIGN,
            buy_lot=1000,
            sell_lot=0,
            buy_value=Decimal("10000000000"),
            sell_value=Decimal("0"),
            avg_buy_price=Decimal("10000"),
            avg_sell_price=Decimal("0"),
        )

        seller = BrokerTransaction(
            broker_code="CC",
            broker_name="Mandiri",
            broker_type=BrokerType.LOCAL,
            buy_lot=0,
            sell_lot=1000,
            buy_value=Decimal("0"),
            sell_value=Decimal("10000000000"),
            avg_buy_price=Decimal("0"),
            avg_sell_price=Decimal("10000"),
        )

        summary = BrokerSummary(
            ticker="BBCA",
            date=date(2024, 1, 15),
            top_buyers=(buyer,),
            top_sellers=(seller,),
            foreign_buy_value=Decimal("50000000000"),  # 50B
            foreign_sell_value=Decimal("30000000000"),  # 30B
            foreign_buy_lot=5000,
            foreign_sell_lot=3000,
            total_value=Decimal("200000000000"),  # 200B
            total_lot=20000,
        )

        assert summary.ticker == "BBCA"
        assert summary.foreign_net_value == Decimal("20000000000")  # 20B
        assert summary.foreign_net_lot == 2000
        assert summary.is_foreign_accumulating is True
        assert summary.foreign_flow_ratio == Decimal("10")  # 20B/200B * 100 = 10%

    def test_foreign_distribution(self):
        """Should correctly identify foreign distribution."""
        summary = BrokerSummary(
            ticker="BBRI",
            date=date(2024, 1, 15),
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("30000000000"),
            foreign_sell_value=Decimal("50000000000"),
            foreign_buy_lot=3000,
            foreign_sell_lot=5000,
            total_value=Decimal("200000000000"),
            total_lot=20000,
        )

        assert summary.foreign_net_value == Decimal("-20000000000")
        assert summary.is_foreign_accumulating is False
        assert summary.foreign_flow_ratio == Decimal("-10")

    def test_zero_total_value_ratio(self):
        """Should handle zero total value."""
        summary = BrokerSummary(
            ticker="TEST",
            date=date(2024, 1, 15),
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("0"),
            foreign_sell_value=Decimal("0"),
            foreign_buy_lot=0,
            foreign_sell_lot=0,
            total_value=Decimal("0"),
            total_lot=0,
        )

        assert summary.foreign_flow_ratio == Decimal("0")

    def test_empty_ticker_raises(self):
        """Should raise for empty ticker."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            BrokerSummary(
                ticker="",
                date=date(2024, 1, 15),
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("0"),
                foreign_sell_value=Decimal("0"),
                foreign_buy_lot=0,
                foreign_sell_lot=0,
                total_value=Decimal("0"),
                total_lot=0,
            )

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        buyer = BrokerTransaction(
            broker_code="YP",
            broker_name="Mirae",
            broker_type=BrokerType.FOREIGN,
            buy_lot=1000,
            sell_lot=0,
            buy_value=Decimal("10000000000"),
            sell_value=Decimal("0"),
            avg_buy_price=Decimal("10000"),
            avg_sell_price=Decimal("0"),
        )

        summary = BrokerSummary(
            ticker="BBCA",
            date=date(2024, 1, 15),
            top_buyers=(buyer,),
            top_sellers=(),
            foreign_buy_value=Decimal("50000000000"),
            foreign_sell_value=Decimal("30000000000"),
            foreign_buy_lot=5000,
            foreign_sell_lot=3000,
            total_value=Decimal("200000000000"),
            total_lot=20000,
        )

        data = summary.to_dict()
        restored = BrokerSummary.from_dict(data)

        assert restored.ticker == summary.ticker
        assert restored.date == summary.date
        assert restored.foreign_net_value == summary.foreign_net_value
        assert len(restored.top_buyers) == 1
        assert restored.top_buyers[0].broker_code == "YP"


class TestBrokerType:
    """Tests for BrokerType enum."""

    def test_broker_types(self):
        """Should have correct broker types."""
        assert BrokerType.FOREIGN.value == "foreign"
        assert BrokerType.LOCAL.value == "local"
        assert BrokerType.UNKNOWN.value == "unknown"
