from datetime import timedelta

import pytest

from src.application.use_case.intraday_backtest_use_case import (
    IntradayBacktestRequest,
    IntradayBacktestUseCase,
)
from tests.application.use_case.intraday_backtest_fixtures import (
    TICKER,
    TRADE_DAY,
    InMemoryBrokerRepository,
    InMemoryMarketRepository,
    StubIndicatorRegistry,
)


def test_validation_empty_tickers_raises():
    use_case = IntradayBacktestUseCase(
        market_repository=InMemoryMarketRepository([]),
        broker_repository=InMemoryBrokerRepository(),
        indicator_registry=StubIndicatorRegistry(),
    )
    with pytest.raises(ValueError, match="ticker"):
        use_case.execute(IntradayBacktestRequest(
            tickers=[],
            start_date=TRADE_DAY,
            end_date=TRADE_DAY,
        ))


def test_validation_start_after_end_raises():
    use_case = IntradayBacktestUseCase(
        market_repository=InMemoryMarketRepository([]),
        broker_repository=InMemoryBrokerRepository(),
        indicator_registry=StubIndicatorRegistry(),
    )
    with pytest.raises(ValueError, match="start_date"):
        use_case.execute(IntradayBacktestRequest(
            tickers=[TICKER],
            start_date=TRADE_DAY,
            end_date=TRADE_DAY - timedelta(days=1),
        ))
