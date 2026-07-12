from datetime import date, timedelta
from decimal import Decimal

from src.domain.entities.broker_flow import BrokerSummary, ForeignFlowPoint
from src.domain.entities.candle import Candle


def _candle(ticker: str, day: date) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("100"),
        volume=1000,
    )


def _generate_candles(ticker: str, start: date, end: date) -> list[Candle]:
    return [_candle(ticker, start + timedelta(days=i)) for i in range((end - start).days + 1)]


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


class FakeBrokerProvider:
    def __init__(
        self,
        provider_name: str = "idx",
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


class EchoLatestBrokerProvider(FakeBrokerProvider):
    def __init__(self, provider_name: str = "stockbit", echo_date: date | None = None) -> None:
        super().__init__(provider_name)
        self.echo_date = echo_date

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        self.requested_ranges.append((start_date, end_date))
        return [_summary(ticker, self.echo_date or end_date, self.provider_name)]


class FakeMarketProvider:
    instances: list["FakeMarketProvider"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.requested_ranges: list[tuple[date, date]] = []
        FakeMarketProvider.instances.append(self)

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        self.requested_ranges.append((start_date, end_date))
        return [_candle(ticker, start_date)]
