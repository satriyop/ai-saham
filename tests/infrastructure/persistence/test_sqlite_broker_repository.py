"""Tests for SQLite broker data repository."""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.entities.broker_flow import (
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def repository(temp_db):
    """Create a repository with temporary database."""
    return SQLiteBrokerRepository(temp_db)


@pytest.fixture
def sample_transaction():
    """Create a sample broker transaction."""
    return BrokerTransaction(
        broker_code="YP",
        broker_name="Mirae Asset",
        broker_type=BrokerType.FOREIGN,
        buy_lot=1000,
        sell_lot=500,
        buy_value=Decimal("10000000000"),
        sell_value=Decimal("5000000000"),
        avg_buy_price=Decimal("10000"),
        avg_sell_price=Decimal("10000"),
    )


@pytest.fixture
def sample_summary(sample_transaction):
    """Create a sample broker summary."""
    return BrokerSummary(
        ticker="BBCA",
        date=date(2024, 1, 15),
        top_buyers=(sample_transaction,),
        top_sellers=(),
        foreign_buy_value=Decimal("50000000000"),
        foreign_sell_value=Decimal("30000000000"),
        foreign_buy_lot=5000,
        foreign_sell_lot=3000,
        total_value=Decimal("200000000000"),
        total_lot=20000,
    )


class TestSQLiteBrokerRepository:
    """Tests for SQLiteBrokerRepository."""

    def test_save_and_retrieve_summary(self, repository, sample_summary):
        """Should save and retrieve a broker summary."""
        repository.save_broker_summary(sample_summary)

        result = repository.get_broker_summary("BBCA", date(2024, 1, 15))

        assert result is not None
        assert result.ticker == "BBCA"
        assert result.date == date(2024, 1, 15)
        assert result.foreign_net_value == Decimal("20000000000")

    def test_save_multiple_summaries(self, repository, sample_transaction):
        """Should save and retrieve multiple summaries."""
        summaries = [
            BrokerSummary(
                ticker="BBCA",
                date=date(2024, 1, 15),
                top_buyers=(sample_transaction,),
                top_sellers=(),
                foreign_buy_value=Decimal("50000000000"),
                foreign_sell_value=Decimal("30000000000"),
                foreign_buy_lot=5000,
                foreign_sell_lot=3000,
                total_value=Decimal("200000000000"),
                total_lot=20000,
            ),
            BrokerSummary(
                ticker="BBCA",
                date=date(2024, 1, 16),
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("60000000000"),
                foreign_sell_value=Decimal("20000000000"),
                foreign_buy_lot=6000,
                foreign_sell_lot=2000,
                total_value=Decimal("250000000000"),
                total_lot=25000,
            ),
        ]

        repository.save_broker_summaries(summaries)

        results = repository.get_broker_summaries("BBCA")
        assert len(results) == 2
        assert results[0].date == date(2024, 1, 15)
        assert results[1].date == date(2024, 1, 16)

    def test_upsert_updates_existing(self, repository, sample_summary):
        """Should update existing summary on save."""
        repository.save_broker_summary(sample_summary)

        # Create updated summary with different values
        updated = BrokerSummary(
            ticker="BBCA",
            date=date(2024, 1, 15),
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("100000000000"),  # Changed
            foreign_sell_value=Decimal("30000000000"),
            foreign_buy_lot=10000,  # Changed
            foreign_sell_lot=3000,
            total_value=Decimal("200000000000"),
            total_lot=20000,
        )
        repository.save_broker_summary(updated)

        result = repository.get_broker_summary("BBCA", date(2024, 1, 15))
        assert result.foreign_buy_value == Decimal("100000000000")
        assert result.foreign_buy_lot == 10000

    def test_get_summaries_with_date_range(self, repository, sample_transaction):
        """Should filter summaries by date range."""
        summaries = [
            BrokerSummary(
                ticker="BBCA",
                date=date(2024, 1, 10),
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("10000000000"),
                foreign_sell_value=Decimal("5000000000"),
                foreign_buy_lot=1000,
                foreign_sell_lot=500,
                total_value=Decimal("50000000000"),
                total_lot=5000,
            ),
            BrokerSummary(
                ticker="BBCA",
                date=date(2024, 1, 15),
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("20000000000"),
                foreign_sell_value=Decimal("10000000000"),
                foreign_buy_lot=2000,
                foreign_sell_lot=1000,
                total_value=Decimal("100000000000"),
                total_lot=10000,
            ),
            BrokerSummary(
                ticker="BBCA",
                date=date(2024, 1, 20),
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("30000000000"),
                foreign_sell_value=Decimal("15000000000"),
                foreign_buy_lot=3000,
                foreign_sell_lot=1500,
                total_value=Decimal("150000000000"),
                total_lot=15000,
            ),
        ]
        repository.save_broker_summaries(summaries)

        # Query with date range
        results = repository.get_broker_summaries(
            "BBCA",
            start_date=date(2024, 1, 12),
            end_date=date(2024, 1, 18),
        )

        assert len(results) == 1
        assert results[0].date == date(2024, 1, 15)

    def test_get_nonexistent_summary(self, repository):
        """Should return None for non-existent summary."""
        result = repository.get_broker_summary("XXXX", date(2024, 1, 15))
        assert result is None

    def test_has_data_returns_true_when_covered(self, repository, sample_summary):
        """Should return True when date range is covered."""
        repository.save_broker_summary(sample_summary)

        assert repository.has_data("BBCA", date(2024, 1, 15), date(2024, 1, 15)) is True

    def test_has_data_returns_false_when_not_covered(self, repository, sample_summary):
        """Should return False when date range is not covered."""
        repository.save_broker_summary(sample_summary)

        assert repository.has_data("BBCA", date(2024, 1, 10), date(2024, 1, 20)) is False

    def test_get_date_range(self, repository, sample_transaction):
        """Should return correct date range."""
        summaries = [
            BrokerSummary(
                ticker="BBCA",
                date=date(2024, 1, 10),
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("0"),
                foreign_sell_value=Decimal("0"),
                foreign_buy_lot=0,
                foreign_sell_lot=0,
                total_value=Decimal("0"),
                total_lot=0,
            ),
            BrokerSummary(
                ticker="BBCA",
                date=date(2024, 1, 20),
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=Decimal("0"),
                foreign_sell_value=Decimal("0"),
                foreign_buy_lot=0,
                foreign_sell_lot=0,
                total_value=Decimal("0"),
                total_lot=0,
            ),
        ]
        repository.save_broker_summaries(summaries)

        result = repository.get_date_range("BBCA")

        assert result == (date(2024, 1, 10), date(2024, 1, 20))

    def test_get_date_range_no_data(self, repository):
        """Should return None when no data exists."""
        result = repository.get_date_range("XXXX")
        assert result is None

    def test_ticker_case_insensitive(self, repository, sample_summary):
        """Should handle ticker case insensitively."""
        repository.save_broker_summary(sample_summary)

        result = repository.get_broker_summary("bbca", date(2024, 1, 15))
        assert result is not None
        assert result.ticker == "BBCA"

    def test_preserves_broker_transactions(self, repository, sample_summary):
        """Should preserve top_buyers and top_sellers through serialization."""
        repository.save_broker_summary(sample_summary)

        result = repository.get_broker_summary("BBCA", date(2024, 1, 15))

        assert len(result.top_buyers) == 1
        assert result.top_buyers[0].broker_code == "YP"
        assert result.top_buyers[0].broker_type == BrokerType.FOREIGN
