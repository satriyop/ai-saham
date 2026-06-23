from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.application.use_case.resolve_opening_prices import (
    ResolveOpeningPricesRequest,
    ResolveOpeningPricesUseCase,
)
from src.domain.entities.trade_tick import TradeTick
from src.domain.value_objects.order_book_snapshot import OrderBookSnapshot

IDX_TZ = ZoneInfo("Asia/Jakarta")


class StubRunningTradeProvider:
    def __init__(self, ticks):
        self._ticks = ticks

    def fetch_running_trade(self, ticker: str, limit: int = 80):
        return self._ticks.get(ticker, [])


class StubOrderBookProvider:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def fetch_snapshot(self, ticker: str):
        return self._snapshots.get(ticker)


def _tick(ticker: str, at: str, price: float, board: str = "RG") -> TradeTick:
    hh, mm, ss = [int(part) for part in at.split(":")]
    return TradeTick(
        ticker=ticker,
        timestamp=datetime(2026, 6, 18, hh, mm, ss, tzinfo=IDX_TZ),
        price=price,
        lot=10,
        buyer_broker_code="AK",
        seller_broker_code="YP",
        trade_type=board,
    )


def _snapshot(ticker: str, last_price: float) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        ticker=ticker,
        captured_at=datetime(2026, 6, 18, 9, 1, tzinfo=IDX_TZ),
        last_price=last_price,
        best_bid_price=last_price - 25,
        best_offer_price=last_price + 25,
        total_bid_lots=1000,
        total_offer_lots=800,
        bid_depth_5=500,
        offer_depth_5=300,
        fnet_intraday=1_000_000_000,
        fbuy_intraday=2_000_000_000,
        fsell_intraday=1_000_000_000,
    )


def test_resolver_prefers_first_regular_running_trade_tick():
    uc = ResolveOpeningPricesUseCase(
        running_trade_provider=StubRunningTradeProvider({
            "BBCA": [
                _tick("BBCA", "09:03:00", 6425),
                _tick("BBCA", "08:59:59", 6400),
                _tick("BBCA", "09:01:00", 6410),
            ]
        }),
        order_book_provider=StubOrderBookProvider({"BBCA": _snapshot("BBCA", 6500)}),
    )

    result = uc.execute(ResolveOpeningPricesRequest(["BBCA"], date(2026, 6, 18)))

    obs = result["BBCA"]
    assert obs.price == Decimal("6410")
    assert obs.source == "running_trade_first_tick"
    assert obs.confidence == "HIGH"
    assert obs.auto_confirmed is True
    assert obs.manual_override is False


def test_resolver_ignores_non_regular_ticks_and_falls_back_to_orderbook():
    uc = ResolveOpeningPricesUseCase(
        running_trade_provider=StubRunningTradeProvider({
            "BBCA": [_tick("BBCA", "09:01:00", 6410, board="NG")]
        }),
        order_book_provider=StubOrderBookProvider({"BBCA": _snapshot("BBCA", 6500)}),
    )

    result = uc.execute(ResolveOpeningPricesRequest(["BBCA"], date(2026, 6, 18)))

    obs = result["BBCA"]
    assert obs.price == Decimal("6500")
    assert obs.source == "order_book_lastprice"
    assert obs.confidence == "MEDIUM"
    assert obs.auto_confirmed is True
    assert obs.manual_override is False


def test_resolver_manual_price_overrides_providers():
    uc = ResolveOpeningPricesUseCase(
        running_trade_provider=StubRunningTradeProvider({"BBCA": [_tick("BBCA", "09:01:00", 6410)]}),
        order_book_provider=StubOrderBookProvider({"BBCA": _snapshot("BBCA", 6500)}),
    )

    result = uc.execute(
        ResolveOpeningPricesRequest(
            ["BBCA"],
            date(2026, 6, 18),
            manual_prices={"BBCA": Decimal("6400")},
        )
    )

    obs = result["BBCA"]
    assert obs.price == Decimal("6400")
    assert obs.source == "manual"
    assert obs.confidence == "HIGH"
    assert obs.auto_confirmed is False
    assert obs.manual_override is True


def test_resolver_reports_progress_for_each_observation():
    progress = []
    uc = ResolveOpeningPricesUseCase(
        running_trade_provider=StubRunningTradeProvider({
            "BBCA": [_tick("BBCA", "09:01:00", 6410)],
            "GOTO": [],
        }),
        order_book_provider=StubOrderBookProvider({}),
        on_observation=lambda index, total, obs: progress.append((index, total, obs)),
    )

    result = uc.execute(ResolveOpeningPricesRequest(["BBCA", "GOTO"], date(2026, 6, 18)))

    assert list(result) == ["BBCA", "GOTO"]
    assert [(item[0], item[1], item[2].ticker) for item in progress] == [
        (1, 2, "BBCA"),
        (2, 2, "GOTO"),
    ]
    assert progress[0][2].price == Decimal("6410")
    assert progress[1][2].price is None
    assert progress[1][2].reason == "no regular-board trade tick at or after 09:00"
