"""
ResolveOpeningPricesUseCase — automatic post-open price resolution.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.domain.ports.order_book_provider import OrderBookProvider
    from src.domain.ports.running_trade_provider import RunningTradeProvider

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.idx_market import REGULAR_OPEN as REGULAR_OPEN_TIME


@dataclass(frozen=True)
class OpeningPriceObservation:
    ticker: str
    price: Decimal | None
    source: str | None
    confidence: str
    timestamp: datetime | None = None
    reason: str | None = None
    auto_confirmed: bool = False
    manual_override: bool = False

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": str(self.price) if self.price is not None else None,
            "source": self.source,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "reason": self.reason,
            "auto_confirmed": self.auto_confirmed,
            "manual_override": self.manual_override,
        }


@dataclass(frozen=True)
class ResolveOpeningPricesRequest:
    tickers: list[str]
    run_date: date
    manual_prices: dict[str, Decimal] | None = None
    track_prices: dict[str, OpeningPriceObservation] | None = None


class ResolveOpeningPricesUseCase:
    """Resolve opening prices using deterministic source precedence."""

    def __init__(
        self,
        running_trade_provider: "RunningTradeProvider | None" = None,
        order_book_provider: "OrderBookProvider | None" = None,
        on_observation: Callable[[int, int, OpeningPriceObservation], None] | None = None,
    ) -> None:
        self._running_trade_provider = running_trade_provider
        self._order_book_provider = order_book_provider
        self._on_observation = on_observation

    def execute(
        self,
        request: ResolveOpeningPricesRequest,
    ) -> dict[str, OpeningPriceObservation]:
        manual = {k.upper(): v for k, v in (request.manual_prices or {}).items()}
        observations: dict[str, OpeningPriceObservation] = {}
        total = len(request.tickers)
        for index, ticker_raw in enumerate(request.tickers, start=1):
            ticker = ticker_raw.upper()
            if ticker in manual:
                observation = OpeningPriceObservation(
                    ticker=ticker,
                    price=manual[ticker],
                    source="manual",
                    confidence="HIGH",
                    reason="manual override",
                    auto_confirmed=False,
                    manual_override=True,
                )
                observations[ticker] = observation
                self._notify(index, total, observation)
                continue
            if request.track_prices and ticker in request.track_prices:
                observation = request.track_prices[ticker]
                observations[ticker] = observation
                self._notify(index, total, observation)
                continue
            observation = self._resolve_auto(ticker, request.run_date)
            observations[ticker] = observation
            self._notify(index, total, observation)
        return observations

    def _notify(
        self,
        index: int,
        total: int,
        observation: OpeningPriceObservation,
    ) -> None:
        if self._on_observation is not None:
            self._on_observation(index, total, observation)

    def _resolve_auto(self, ticker: str, run_date: date) -> OpeningPriceObservation:
        tick_obs = self._from_running_trade(ticker, run_date)
        if tick_obs.price is not None:
            return tick_obs

        ob_obs = self._from_order_book(ticker)
        if ob_obs.price is not None:
            return ob_obs

        return OpeningPriceObservation(
            ticker=ticker,
            price=None,
            source=None,
            confidence="NONE",
            reason=tick_obs.reason or ob_obs.reason or "no usable opening price",
        )

    def _from_running_trade(self, ticker: str, run_date: date) -> OpeningPriceObservation:
        if self._running_trade_provider is None:
            return OpeningPriceObservation(
                ticker=ticker,
                price=None,
                source="running_trade",
                confidence="NONE",
                reason="running trade provider unavailable",
            )

        try:
            ticks = self._running_trade_provider.fetch_running_trade(ticker, limit=500)
        except Exception as exc:
            return OpeningPriceObservation(
                ticker=ticker,
                price=None,
                source="running_trade",
                confidence="NONE",
                reason=f"running trade failed: {exc}",
            )

        eligible = []
        for tick in ticks:
            ts = tick.timestamp.astimezone(IDX_TIMEZONE)
            board = (tick.trade_type or "").upper()
            if ts.date() != run_date:
                continue
            if ts.time() < REGULAR_OPEN_TIME:
                continue
            if board in {"NG", "TN", "NEGOTIATED", "CASH", "BOARD_TYPE_NEGOTIATED"}:
                continue
            eligible.append(tick)

        if not eligible:
            return OpeningPriceObservation(
                ticker=ticker,
                price=None,
                source="running_trade",
                confidence="NONE",
                reason="no regular-board trade tick at or after 09:00",
            )

        first_tick = min(eligible, key=lambda tick: tick.timestamp)
        return OpeningPriceObservation(
            ticker=ticker,
            price=Decimal(str(first_tick.price)),
            source="running_trade_first_tick",
            confidence="HIGH",
            timestamp=first_tick.timestamp.astimezone(IDX_TIMEZONE),
            reason="first regular-board tick at or after 09:00",
            auto_confirmed=True,
            manual_override=False,
        )

    def _from_order_book(self, ticker: str) -> OpeningPriceObservation:
        if self._order_book_provider is None:
            return OpeningPriceObservation(
                ticker=ticker,
                price=None,
                source="order_book",
                confidence="NONE",
                reason="order book provider unavailable",
            )

        try:
            snapshot = self._order_book_provider.fetch_snapshot(ticker)
        except Exception as exc:
            return OpeningPriceObservation(
                ticker=ticker,
                price=None,
                source="order_book",
                confidence="NONE",
                reason=f"order book failed: {exc}",
            )

        if snapshot is None:
            return OpeningPriceObservation(
                ticker=ticker,
                price=None,
                source="order_book",
                confidence="NONE",
                reason="order book unavailable",
            )

        if snapshot.last_price and snapshot.last_price > 0:
            return OpeningPriceObservation(
                ticker=ticker,
                price=Decimal(str(snapshot.last_price)),
                source="order_book_lastprice",
                confidence="MEDIUM",
                timestamp=(
                    snapshot.captured_at.astimezone(IDX_TIMEZONE)
                    if snapshot.captured_at.tzinfo
                    else snapshot.captured_at.replace(tzinfo=IDX_TIMEZONE)
                ),
                reason="Stockbit orderbook lastprice fallback",
                auto_confirmed=True,
                manual_override=False,
            )

        if snapshot.best_bid_price > 0 and snapshot.best_offer_price > 0:
            midpoint = (snapshot.best_bid_price + snapshot.best_offer_price) / 2
            return OpeningPriceObservation(
                ticker=ticker,
                price=Decimal(str(round(midpoint, 2))),
                source="top_of_book_midpoint",
                confidence="LOW",
                timestamp=(
                    snapshot.captured_at.astimezone(IDX_TIMEZONE)
                    if snapshot.captured_at.tzinfo
                    else snapshot.captured_at.replace(tzinfo=IDX_TIMEZONE)
                ),
                reason="midpoint fallback; not an execution price",
                auto_confirmed=True,
                manual_override=False,
            )

        return OpeningPriceObservation(
            ticker=ticker,
            price=None,
            source="order_book",
            confidence="NONE",
            reason="order book has no lastprice or bid/offer fallback",
        )
