"""
OpeningTrackUseCase — 5-minute orderbook tracker for the opening session (09:00–09:30 WIB).

For every ticker in today's snapshot, fetches bid/offer from Stockbit every 5 minutes
and saves to data/opening/YYYYMMDD/track_HHMM.json. Loops internally until 09:31 WIB.

Optional --broker-confirm mode: also fetches running-trade ticks per ticker each interval
and embeds a RunningTradeSignal in the track JSON under tickers[ticker]["broker_signal"].

Layer: Application
"""

from __future__ import annotations

import json
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from src.domain.ports.order_book_provider import OrderBookProvider
    from src.domain.ports.running_trade_provider import RunningTradeProvider

IDX_TIMEZONE = ZoneInfo("Asia/Jakarta")
OPENING_DATA_DIR = Path("data/opening")

TRACK_START = time(9, 0)
TRACK_END = time(9, 31)
INTERVAL_MINUTES = 5


@dataclass(frozen=True)
class OpeningTrackRequest:
    tickers: list[str]
    run_date: date | None = None
    force: bool = False
    broker_confirm: bool = False
    institutional_broker_codes: frozenset[str] = frozenset()
    order_book: bool = False    # embed full order book depth + live foreign net per snapshot


class OpeningTrackUseCase:
    """Fetch orderbook top-of-book every 5 min from 09:00–09:30 WIB for tracked tickers.

    Args:
        browser:                 Playwright Stockbit browser for orderbook fetches.
        running_trade_provider:  Optional provider for broker confirmation ticks.
                                 Only used when request.broker_confirm is True.
    """

    def __init__(
        self,
        browser,
        running_trade_provider: "RunningTradeProvider | None" = None,
        order_book_provider: "OrderBookProvider | None" = None,
    ) -> None:
        self._browser = browser
        self._running_trade_provider = running_trade_provider
        self._order_book_provider = order_book_provider

    def execute(self, request: OpeningTrackRequest) -> list[dict]:
        now = datetime.now(IDX_TIMEZONE)
        run_date = request.run_date or now.date()
        out_dir = OPENING_DATA_DIR / run_date.strftime("%Y%m%d")
        out_dir.mkdir(parents=True, exist_ok=True)

        snapshots: list[dict] = []

        if request.force:
            # Manual/dry-run: single immediate snapshot
            snapshot = self._capture(request.tickers, request)
            label = datetime.now(IDX_TIMEZONE).strftime("%H%M")
            self._save(out_dir, label, snapshot)
            snapshots.append(snapshot)
            return snapshots

        # Live mode: loop every 5 minutes from 09:00 to 09:30
        while True:
            now = datetime.now(IDX_TIMEZONE)
            current = now.time().replace(second=0, microsecond=0)

            if current > TRACK_END:
                break

            if current >= TRACK_START:
                snapshot = self._capture(request.tickers, request)
                label = now.strftime("%H%M")
                self._save(out_dir, label, snapshot)
                snapshots.append(snapshot)

            # Wait until the next 5-minute mark
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
                    bid_lots = tob.bid.volume or 0
                    offer_lots = tob.offer.volume or 0
                    total_lots = bid_lots + offer_lots
                    entry = {
                        "best_bid": bid,
                        "best_offer": offer,
                        "bid_lots": bid_lots,
                        "offer_lots": offer_lots,
                        "mid_price": round((bid + offer) / 2, 2),
                        "spread": round(offer - bid, 2),
                        "bid_pressure": round(bid_lots / total_lots, 4) if total_lots > 0 else None,
                    }
                else:
                    entry = {}
            except Exception as e:
                entry = {"error": str(e)}

            # Optional broker confirmation — embed RunningTradeSignal if provider available
            if request.broker_confirm and self._running_trade_provider is not None and not entry.get("error"):
                try:
                    from src.application.use_case.analyze_running_trade import (
                        AnalyzeRunningTradeRequest,
                        analyze_running_trade,
                    )
                    ticks = self._running_trade_provider.fetch_running_trade(ticker)
                    signal = analyze_running_trade(AnalyzeRunningTradeRequest(
                        ticker=ticker,
                        ticks=ticks,
                        institutional_broker_codes=request.institutional_broker_codes,
                    ))
                    entry["broker_signal"] = signal.to_dict() if signal else None
                except Exception:
                    entry["broker_signal"] = None

            # Optional order book depth — bid pressure + live foreign net
            if request.order_book and self._order_book_provider is not None and not entry.get("error"):
                try:
                    ob = self._order_book_provider.fetch_snapshot(ticker)
                    entry["order_book"] = ob.to_dict() if ob else None
                except Exception:
                    entry["order_book"] = None

            ticker_data[ticker] = entry if entry else None

        return {
            "captured_at": now.isoformat(),
            "tickers": ticker_data,
        }

    @staticmethod
    def _save(out_dir: Path, label: str, snapshot: dict) -> None:
        path = out_dir / f"track_{label}.json"
        with open(path, "w") as f:
            json.dump(snapshot, f, indent=2)

    @staticmethod
    def _seconds_to_next_interval(now: datetime) -> int:
        """Seconds until the next 5-minute boundary (e.g. 09:05, 09:10, ...)."""
        current_minute = now.minute
        next_minute = ((current_minute // INTERVAL_MINUTES) + 1) * INTERVAL_MINUTES
        wait_minutes = next_minute - current_minute
        wait_seconds = wait_minutes * 60 - now.second
        return max(0, wait_seconds)
