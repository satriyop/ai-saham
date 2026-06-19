"""Tests for broker refresh application use case."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.use_case.refresh_broker_data import (
    RefreshBrokerDataRequest,
    RefreshBrokerDataUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary, ForeignFlowPoint
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository


def _summary(ticker: str, day: date, source: str = "idx") -> BrokerSummary:
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=Decimal("1000"),
        foreign_sell_value=Decimal("500"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("10000"),
        total_lot=100,
        source=source,
    )


def _daily_flow(ticker: str, day: date, broker_code: str = "AK") -> BrokerDailyFlow:
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=broker_code,
        broker_name=broker_code,
        date=day,
        buy_lot=10,
        sell_lot=5,
        net_lot=5,
        buy_value=Decimal("1000"),
        sell_value=Decimal("500"),
        net_value=Decimal("500"),
        avg_buy_price=Decimal("100"),
        avg_sell_price=Decimal("100"),
        avg_price=Decimal("100"),
        buy_pct=1.0,
        sell_pct=0.5,
        source="stockbit",
    )


class FakeBrokerProvider:
    def __init__(
        self,
        provider_name: str = "stockbit",
        historical_points: list[ForeignFlowPoint] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.historical_points = historical_points or []
        self.requested_ranges: list[tuple[date, date]] = []

    def is_authenticated(self) -> bool:
        return True

    def fetch_broker_summary(self, ticker: str, target_date: date):
        return _summary(ticker, target_date, self.provider_name)

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        self.requested_ranges.append((start_date, end_date))
        return [_summary(ticker, start_date, self.provider_name)]

    def fetch_foreign_flow_history(
        self,
        ticker: str,
        days: int = 365,
    ) -> list[ForeignFlowPoint]:
        return self.historical_points


class FakeDailyBrokerProvider(FakeBrokerProvider):
    def __init__(
        self,
        daily_flows: list[BrokerDailyFlow],
        historical_points: list[ForeignFlowPoint] | None = None,
    ) -> None:
        super().__init__("stockbit", historical_points=historical_points)
        self.daily_flows = daily_flows
        self.daily_fetch_count = 0

    def fetch_broker_daily_flows(
        self,
        ticker: str,
        broker_codes: list[str] | None = None,
        days: int = 365,
    ) -> list[BrokerDailyFlow]:
        self.daily_fetch_count += 1
        return self.daily_flows


def test_refresh_broker_checks_idx_summaries_independently_from_stockbit_flow(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    end_date = date(2026, 6, 18)
    requested_start = date(2025, 6, 18)
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=end_date,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        )
    ])
    stockbit_provider = FakeBrokerProvider("stockbit")
    idx_provider = FakeBrokerProvider("idx")

    response = RefreshBrokerDataUseCase(
        broker_provider=stockbit_provider,
        idx_summary_provider=idx_provider,
        repository=repo,
    ).execute(
        RefreshBrokerDataRequest(
            ticker="BBCA",
            days=365,
            end_date=end_date,
            last_trading_day=end_date,
        )
    )

    assert idx_provider.requested_ranges == [(requested_start, end_date)]
    assert response.summaries_status.startswith("+")
    assert response.flow_status == f"agg=✓({end_date})"


def test_refresh_broker_reports_cached_current_without_provider_fetch(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    end_date = date(2026, 6, 18)
    requested_start = date(2025, 6, 18)
    repo.save_broker_summary(_summary("BBCA", requested_start, "idx"))
    repo.save_broker_summary(_summary("BBCA", end_date, "idx"))
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=requested_start,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        ),
        ForeignFlowPoint(
            ticker="BBCA",
            date=end_date,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        ),
    ])
    stockbit_provider = FakeBrokerProvider("stockbit")
    idx_provider = FakeBrokerProvider("idx")

    response = RefreshBrokerDataUseCase(
        broker_provider=stockbit_provider,
        idx_summary_provider=idx_provider,
        repository=repo,
    ).execute(
        RefreshBrokerDataRequest(
            ticker="BBCA",
            days=365,
            end_date=end_date,
            last_trading_day=end_date,
        )
    )

    assert idx_provider.requested_ranges == []
    assert response.summaries_status == f"✓({end_date})"
    assert response.flow_status == f"agg=✓({end_date})"


def test_refresh_broker_fetches_daily_flow_until_expected_latest_trading_day(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteBrokerRepository(db_path)
    end_date = date(2026, 6, 18)
    expected_latest = date(2026, 6, 17)
    stale_daily = date(2026, 6, 12)
    requested_start = date(2025, 6, 18)
    repo.save_broker_summary(_summary("BBCA", requested_start, "idx"))
    repo.save_broker_summary(_summary("BBCA", expected_latest, "idx"))
    repo.save_foreign_flow_points([
        ForeignFlowPoint(
            ticker="BBCA",
            date=expected_latest,
            net_val=Decimal("100"),
            net_lot=1,
            avg_price=Decimal("1000"),
            source="stockbit",
        )
    ])
    repo.save_broker_daily_flows([_daily_flow("BBCA", stale_daily)])
    stockbit_provider = FakeDailyBrokerProvider([_daily_flow("BBCA", expected_latest)])
    idx_provider = FakeBrokerProvider("idx")

    response = RefreshBrokerDataUseCase(
        broker_provider=stockbit_provider,
        idx_summary_provider=idx_provider,
        repository=repo,
    ).execute(
        RefreshBrokerDataRequest(
            ticker="BBCA",
            days=365,
            end_date=end_date,
            last_trading_day=expected_latest,
        )
    )

    assert stockbit_provider.daily_fetch_count == 1
    assert response.flow_status.startswith("daily:+1rows/")
    assert repo.get_broker_daily_flow_date_range("BBCA", source="stockbit") == (
        stale_daily,
        expected_latest,
    )
