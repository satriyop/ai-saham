from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import AgentToolExecutionStatus
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_broker_desk_tool import (
    BrokerDeskArguments,
    BrokerDeskResultData,
    BrokerDeskTool,
    BrokerDeskUseCases,
)
from src.application.services.broker_desk_from_daily_flow import (
    DeskCalendarDay,
    DeskDayNet,
    DeskTickerNet,
    DeskTickerWindowCell,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerType
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _ticker_net(ticker: str, net: str) -> DeskTickerNet:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
    return DeskTickerNet(
        ticker=ticker,
        net_value=value,
        net_lot=10 if value > 0 else -10,
        buy_value=buy,
        sell_value=sell,
        sessions=1,
    )


def _flow(ticker: str, d: date, net: str, code: str = "YP") -> BrokerDailyFlow:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
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
        net_value=value,
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal("1000"),
        buy_pct=0.0,
        sell_pct=0.0,
    )


class _DeskFakes:
    def __init__(self, *, missing: bool = False, history_rows: int = 2) -> None:
        self.missing = missing
        self.history_rows = history_rows
        self.calls: list[tuple[str, object]] = []

    def show(self, request):
        self.calls.append(("SHOW", request))
        if self.missing:
            return None
        return SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 8, 1),
            day_net_value=Decimal("1500"),
            day_net_lot=12,
            day_ticker_count=2,
            top_buy_stocks=(_ticker_net("BBCA", "1000"),),
            top_sell_stocks=(_ticker_net("TLKM", "-500"),),
            scope_note="Tracked desk activity only (broker_daily_flow)",
        )

    def top_stocks(self, request):
        self.calls.append(("TOP_STOCKS", request))
        if self.missing:
            return None
        return SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            date=date(2026, 8, 1),
            top_buy_stocks=(_ticker_net("BBCA", "1000"),),
            top_sell_stocks=(_ticker_net("TLKM", "-500"),),
            scope_note="Tracked desk activity only (broker_daily_flow)",
        )

    def top_matrix(self, request):
        self.calls.append(("TOP_MATRIX", request))
        if self.missing:
            return None
        return SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 8, 1),
            windows=(1, 3),
            columns={
                1: (
                    DeskTickerWindowCell(
                        ticker="BBCA",
                        net_value=Decimal("1000"),
                        window=1,
                        sessions_used=1,
                        avg_buy_price=Decimal("1025"),
                        buy_streak=2,
                        is_partial=False,
                    ),
                ),
                3: (
                    DeskTickerWindowCell(
                        ticker="BBCA",
                        net_value=Decimal("2500"),
                        window=3,
                        sessions_used=2,
                        avg_buy_price=None,
                        buy_streak=1,
                        is_partial=True,
                    ),
                ),
            },
            sessions_cached=2,
            top_ticker_1s="BBCA",
            scope_note="Tracked desk activity only",
        )

    def flow(self, request):
        self.calls.append(("FLOW", request))
        if self.missing:
            return None
        return SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            days=(
                DeskDayNet(
                    date=date(2026, 7, 31),
                    net_value=Decimal("100"),
                    net_lot=1,
                    buy_value=Decimal("100"),
                    sell_value=Decimal("0"),
                    ticker_count=1,
                ),
                DeskDayNet(
                    date=date(2026, 8, 1),
                    net_value=Decimal("200"),
                    net_lot=2,
                    buy_value=Decimal("200"),
                    sell_value=Decimal("0"),
                    ticker_count=1,
                ),
            ),
            scope_note="Tracked desk activity only (broker_daily_flow)",
        )

    def calendar(self, request):
        self.calls.append(("CALENDAR", request))
        if self.missing:
            return None
        return SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 8, 1),
            days=(
                DeskCalendarDay(
                    date=date(2026, 8, 1),
                    net_value=Decimal("300"),
                    buy_value=Decimal("400"),
                    sell_value=Decimal("100"),
                    top_ticker="BBCA",
                    top_net=Decimal("300"),
                    ticker_count=2,
                ),
            ),
            sessions_cached=1,
            scope_note="Tracked desk activity only · day cells",
        )

    def history(self, request):
        self.calls.append(("HISTORY", request))
        if self.missing:
            return None
        flows = tuple(
            _flow("BBCA", date(2026, 8, 1) - __import__("datetime").timedelta(days=i), "10")
            for i in range(self.history_rows)
        )
        return SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            flows=flows,
            pinned_ticker=None,
            scope_note="Tracked desk activity only (broker_daily_flow)",
        )


def _tool(fake: _DeskFakes) -> BrokerDeskTool:
    return BrokerDeskTool(
        BrokerDeskUseCases(
            show=SimpleNamespace(execute=fake.show),
            top_stocks=SimpleNamespace(execute=fake.top_stocks),
            top_matrix=SimpleNamespace(execute=fake.top_matrix),
            flow=SimpleNamespace(execute=fake.flow),
            calendar=SimpleNamespace(execute=fake.calendar),
            history=SimpleNamespace(execute=fake.history),
        )
    )


def test_show_view_returns_bounded_success_projection() -> None:
    fake = _DeskFakes()
    tool = _tool(fake)

    result = tool.execute(
        "desk-show",
        BrokerDeskArguments("YP", "SHOW"),
        _context(),
    )

    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, BrokerDeskResultData)
    assert result.data.schema_id == "agent_tool.broker_desk.result.v1"
    assert result.data.view == "SHOW"
    assert result.data.broker_code == "YP"
    assert result.data.show is not None
    assert result.data.show.day_net_value_idr == "1500"
    assert result.data.show.top_buy_stocks[0].ticker == "BBCA"
    assert result.data.top_stocks is None
    assert result.provenance.source == "broker-desk-cache"
    assert result.source_reference == "broker-desk:YP:SHOW:2026-08-01"
    assert result.serialized_size() <= tool.definition.max_result_bytes
    assert fake.calls == [("SHOW", fake.calls[0][1])]


def test_each_named_view_dispatches_exactly_one_use_case() -> None:
    for view in ("SHOW", "TOP_STOCKS", "TOP_MATRIX", "FLOW", "CALENDAR", "HISTORY"):
        fake = _DeskFakes()
        tool = _tool(fake)
        result = tool.execute("desk", BrokerDeskArguments("YP", view), _context())
        assert result.status in {
            AgentToolExecutionStatus.SUCCESS,
            AgentToolExecutionStatus.PARTIAL,
        }
        assert [name for name, _ in fake.calls] == [view]


def test_partial_matrix_and_truncated_history() -> None:
    matrix = _tool(_DeskFakes()).execute(
        "matrix",
        BrokerDeskArguments("YP", "TOP_MATRIX"),
        _context(),
    )
    assert matrix.status is AgentToolExecutionStatus.PARTIAL
    assert "partial session windows" in matrix.warnings[0]

    history = _tool(_DeskFakes(history_rows=45)).execute(
        "history",
        BrokerDeskArguments("YP", "HISTORY"),
        _context(),
    )
    assert history.status is AgentToolExecutionStatus.PARTIAL
    assert history.data is not None
    assert history.data.history is not None
    assert history.data.history.total_row_count == 45
    assert history.data.history.truncated_row_count == 5
    assert len(history.data.history.rows) == 40


def test_missing_cache_is_unavailable() -> None:
    tool = _tool(_DeskFakes(missing=True))
    result = tool.execute("missing", BrokerDeskArguments("YP", "SHOW"), _context())
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.error_code == "BROKER_DESK_UNAVAILABLE"
    assert result.data is None


def test_broken_use_case_fails_without_raw_details() -> None:
    class Broken:
        def execute(self, request):
            raise RuntimeError("secret sql path")

    tool = BrokerDeskTool(
        BrokerDeskUseCases(
            show=Broken(),
            top_stocks=Broken(),
            top_matrix=Broken(),
            flow=Broken(),
            calendar=Broken(),
            history=Broken(),
        )
    )
    result = tool.execute("broken", BrokerDeskArguments("YP", "SHOW"), _context())
    assert result.status is AgentToolExecutionStatus.FAILED
    assert result.error_code == "BROKER_DESK_READ_FAILED"
    assert "secret" not in (result.error_message or "")


@pytest.mark.parametrize(
    ("code", "view"),
    (
        ("yp", "SHOW"),
        ("YPP", "SHOW"),
        ("Y", "SHOW"),
        ("YP", "show"),
        ("YP", "TOP"),
    ),
)
def test_invalid_arguments_rejected(code: str, view: str) -> None:
    with pytest.raises(ValueError):
        BrokerDeskArguments(code, view)
