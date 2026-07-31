"""ViewBrokerDeskCalendarUseCase."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.use_case.view_broker_desk_calendar_use_case import (
    ViewBrokerDeskCalendarRequest,
    ViewBrokerDeskCalendarUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow


def _flow(ticker: str, d: date, net: str, code: str = "YP") -> BrokerDailyFlow:
    nv = Decimal(net)
    buy = nv if nv > 0 else Decimal("0")
    sell = -nv if nv < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=code,
        broker_name="YP Desk",
        date=d,
        buy_lot=1 if buy else 0,
        sell_lot=1 if sell else 0,
        net_lot=1 if buy else -1,
        buy_value=buy,
        sell_value=sell,
        net_value=nv,
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal("1000"),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def test_calendar_none_when_empty():
    repo = MagicMock()
    repo.get_broker_daily_flows_by_code.return_value = []
    uc = ViewBrokerDeskCalendarUseCase(repo)
    assert uc.execute(ViewBrokerDeskCalendarRequest(broker_code="YP")) is None


def test_calendar_result_scope_not_market_foreign():
    repo = MagicMock()
    repo.get_broker_daily_flows_by_code.return_value = [
        _flow("AMMN", date(2026, 7, 29), "100"),
    ]
    uc = ViewBrokerDeskCalendarUseCase(repo, foreign_broker_codes=frozenset({"YP"}))
    result = uc.execute(ViewBrokerDeskCalendarRequest(broker_code="yp"))
    assert result is not None
    assert result.broker_code == "YP"
    assert result.days[0].top_ticker == "AMMN"
    assert "not market foreign" in result.scope_note.lower()
    assert "Tracked desk" in result.scope_note
