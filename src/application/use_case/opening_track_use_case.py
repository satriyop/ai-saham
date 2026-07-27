"""
OpeningTrackUseCase — 5-minute orderbook tracker for the opening session (09:00–09:30 WIB).

For every saved pre-open observation, fetches bid/offer from Stockbit every
5 minutes and persists an immutable database track snapshot linked to its
observation. Loops internally until 09:31 WIB.

Each tick entry always includes full order book depth (bid_pressure_ratio, depth_ratio_5,
fnet_intraday) when order_book_provider is wired — this replaces the old naive top-of-book
bid_pressure field which only covered 1 price level.

Optional --broker-confirm mode: also fetches running-trade ticks per ticker each interval
and embeds a RunningTradeSignal in the track JSON under tickers[ticker]["broker_signal"].

Layer: Application
"""

from __future__ import annotations

import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Mapping

from src.domain.value_objects.learning_artifacts import LearningTrackSnapshot

if TYPE_CHECKING:
    from src.domain.ports.learning_artifact_repositories import (
        LearningTrackSnapshotRepository,
    )
    from src.domain.ports.order_book_provider import OrderBookProvider
    from src.domain.ports.running_trade_provider import RunningTradeProvider

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.idx_market import REGULAR_OPEN as TRACK_START

TRACK_END = time(9, 31)
INTERVAL_MINUTES = 5


@dataclass(frozen=True)
class OpeningTrackRequest:
    observation_ids_by_ticker: Mapping[str, str]
    run_date: date | None = None
    force: bool = False
    broker_confirm: bool = False
    institutional_broker_codes: frozenset[str] = frozenset()


class OpeningTrackUseCase:
    """Fetch orderbook every 5 min from 09:00–09:30 WIB for tracked tickers.

    Args:
        browser:                 Playwright Stockbit browser for top-of-book fetches
                                 (best_bid, best_offer, mid_price, spread).
        running_trade_provider:  Optional provider for broker confirmation ticks.
                                 Only used when request.broker_confirm is True.
        order_book_provider:     Optional provider for full order book depth.
                                 When wired, embeds bid_pressure_ratio (all levels),
                                 depth_ratio_5, fnet_intraday per snapshot.
    """

    def __init__(
        self,
        browser,
        repository: "LearningTrackSnapshotRepository",
        running_trade_provider: "RunningTradeProvider | None" = None,
        order_book_provider: "OrderBookProvider | None" = None,
    ) -> None:
        self._browser = browser
        self._repository = repository
        self._running_trade_provider = running_trade_provider
        self._order_book_provider = order_book_provider

    def execute(self, request: OpeningTrackRequest) -> list[dict]:
        now = datetime.now(IDX_TIMEZONE)
        snapshots: list[dict] = []

        if request.force:
            snapshot = self._capture(list(request.observation_ids_by_ticker), request)
            self._persist(snapshot, request)
            snapshots.append(snapshot)
            return snapshots

        # Live mode: loop every 5 minutes from 09:00 to 09:30
        while True:
            now = datetime.now(IDX_TIMEZONE)
            current = now.time().replace(second=0, microsecond=0)

            if current > TRACK_END:
                break

            if current >= TRACK_START:
                snapshot = self._capture(list(request.observation_ids_by_ticker), request)
                self._persist(snapshot, request)
                snapshots.append(snapshot)

            seconds_to_next = self._seconds_to_next_interval(now)
            if seconds_to_next > 0 and datetime.now(IDX_TIMEZONE).time() < TRACK_END:
                time_module.sleep(min(seconds_to_next, 30))
            elif datetime.now(IDX_TIMEZONE).time() >= TRACK_END:
                break

        return snapshots

    def _capture(self, tickers: list[str], request: OpeningTrackRequest) -> dict:
        now = datetime.now(IDX_TIMEZONE)
        ticker_data = {}
        for ticker in tickers:
            entry: dict = {}
            try:
                tob = self._browser.fetch_order_book_top_of_book(ticker)
                if tob and tob.bid and tob.offer:
                    bid = float(tob.bid.price)
                    offer = float(tob.offer.price)
                    entry = {
                        "best_bid": bid,
                        "best_offer": offer,
                        "mid_price": round((bid + offer) / 2, 2),
                        "mid_price_source": "top_of_book_midpoint",
                        "mid_price_confidence": "LOW",
                        "spread": round(offer - bid, 2),
                    }
                else:
                    entry = {}
            except Exception as e:
                entry = {"error": str(e)}

            # Full order book depth — bid_pressure_ratio (all levels), fnet_intraday
            if self._order_book_provider is not None and not entry.get("error"):
                try:
                    ob = self._order_book_provider.fetch_snapshot(ticker)
                    entry["order_book"] = ob.to_dict() if ob else None
                except Exception:
                    entry["order_book"] = None

            # Optional broker confirmation — RunningTradeSignal
            if (
                request.broker_confirm
                and self._running_trade_provider is not None
                and not entry.get("error")
            ):
                try:
                    from src.application.use_case.analyze_running_trade_use_case import (
                        AnalyzeRunningTradeRequest,
                        analyze_running_trade,
                    )

                    ticks = self._running_trade_provider.fetch_running_trade(ticker)
                    signal = analyze_running_trade(
                        AnalyzeRunningTradeRequest(
                            ticker=ticker,
                            ticks=ticks,
                            institutional_broker_codes=request.institutional_broker_codes,
                        )
                    )
                    entry["broker_signal"] = signal.to_dict() if signal else None
                except Exception:
                    entry["broker_signal"] = None

            # Promote explicit opening_price only (never mid_price as open).
            self._promote_opening_price(entry, sampled_at=now)

            ticker_data[ticker] = entry if entry else None

        return {
            "captured_at": now.isoformat(),
            "tickers": ticker_data,
        }

    def _persist(self, snapshot: dict, request: OpeningTrackRequest) -> None:
        sampled_at = datetime.fromisoformat(snapshot["captured_at"])
        for ticker, payload in snapshot["tickers"].items():
            observation_id = request.observation_ids_by_ticker[ticker]
            self._repository.add_track_snapshot(
                LearningTrackSnapshot.create(
                    observation_id=observation_id,
                    sampled_at=sampled_at,
                    source="stockbit.opening_track",
                    snapshot_payload=payload or {"availability": "UNAVAILABLE"},
                    captured_at=sampled_at,
                )
            )

    @staticmethod
    def _promote_opening_price(entry: dict, *, sampled_at: datetime) -> None:
        """Set top-level opening_price from order_book last trade when valid.

        Assess/analyze require an explicit ``opening_price`` key. Nested
        ``order_book.last_price`` alone is not enough. Mid-of-book must never
        be promoted as open.
        """
        if not entry or entry.get("error"):
            return
        if entry.get("opening_price") is not None:
            try:
                if float(entry["opening_price"]) > 0:
                    entry.setdefault(
                        "opening_price_source",
                        entry.get("opening_price_source") or "order_book_lastprice",
                    )
                    entry.setdefault("opening_price_confidence", "MEDIUM")
                    entry.setdefault("opening_price_timestamp", sampled_at.isoformat())
                    return
            except (TypeError, ValueError):
                entry.pop("opening_price", None)

        candidates: list[object] = []
        order_book = entry.get("order_book")
        if isinstance(order_book, dict):
            for key in ("last_price", "lastprice", "close"):
                if order_book.get(key) is not None:
                    candidates.append(order_book.get(key))
        # Already on entry from a future producer path
        for key in ("last_price", "lastprice"):
            if entry.get(key) is not None:
                candidates.append(entry.get(key))

        for raw in candidates:
            try:
                price = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            entry["opening_price"] = price
            entry["opening_price_source"] = "order_book_lastprice"
            entry["opening_price_confidence"] = "MEDIUM"
            entry["opening_price_timestamp"] = sampled_at.isoformat()
            return

        # Explicit absence for status/consumers (mid may still be present)
        entry["opening_price_status"] = "MISSING"

    @staticmethod
    def _seconds_to_next_interval(now: datetime) -> int:
        """Seconds until the next 5-minute boundary (e.g. 09:05, 09:10, ...)."""
        current_minute = now.minute
        next_minute = ((current_minute // INTERVAL_MINUTES) + 1) * INTERVAL_MINUTES
        wait_minutes = next_minute - current_minute
        wait_seconds = wait_minutes * 60 - now.second
        return max(0, wait_seconds)
