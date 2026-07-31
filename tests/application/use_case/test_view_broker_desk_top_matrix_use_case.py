"""ViewBrokerDeskTopMatrixUseCase — matrix from repository flows."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.use_case.view_broker_desk_top_matrix_use_case import (
    ViewBrokerDeskTopMatrixRequest,
    ViewBrokerDeskTopMatrixUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow


def _flow(
    ticker: str,
    d: date,
    net: str,
    *,
    code: str = "YP",
    buy_lot: int = 10,
    avg_buy: str = "1000",
) -> BrokerDailyFlow:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=code,
        broker_name="YP Desk",
        date=d,
        buy_lot=buy_lot if buy else 0,
        sell_lot=buy_lot if sell else 0,
        net_lot=buy_lot if buy else -buy_lot,
        buy_value=buy,
        sell_value=sell,
        net_value=value,
        avg_buy_price=Decimal(avg_buy),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal(avg_buy),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def test_execute_none_when_no_flows():
    repo = MagicMock()
    repo.get_broker_daily_flows_by_code.return_value = []
    uc = ViewBrokerDeskTopMatrixUseCase(repo)
    assert uc.execute(ViewBrokerDeskTopMatrixRequest(broker_code="YP")) is None


def test_execute_matrix_and_top_ticker_1s():
    base = date(2026, 7, 20)
    flows = [_flow("AMMN", base + timedelta(days=i), "20", avg_buy="9000") for i in range(3)] + [
        _flow("BUMI", base + timedelta(days=i), "10", avg_buy="150") for i in range(3)
    ]
    repo = MagicMock()
    repo.get_broker_daily_flows_by_code.return_value = flows
    uc = ViewBrokerDeskTopMatrixUseCase(repo, foreign_broker_codes=frozenset({"YP"}))
    result = uc.execute(ViewBrokerDeskTopMatrixRequest(broker_code="yp", limit=5))
    assert result is not None
    assert result.broker_code == "YP"
    assert result.as_of == base + timedelta(days=2)
    assert result.sessions_cached == 3
    assert result.top_ticker_1s == "AMMN"
    assert result.columns[1][0].ticker == "AMMN"
    assert result.columns[3][0].is_partial is False  # exactly 3 sessions
    assert result.columns[5][0].is_partial is True
    assert "Tracked desk" in result.scope_note
