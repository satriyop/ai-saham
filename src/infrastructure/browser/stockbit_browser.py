"""
Stockbit browser data adapters.

Two concrete implementations of BrowserDataProvider:

1. ManualBrowserDataProvider — accepts pre-fetched data (JSON dicts).
   Used when Claude Code has already navigated the browser and extracted the data.

2. StockbitBrowserInstructionsProvider — raises BrowserInteractionRequired with
   precise step-by-step instructions for Claude Code to follow.
   Used when no pre-fetched data is available.

Layer: Infrastructure
"""

from decimal import Decimal

from src.domain.ports.browser_data_provider import (
    BrowserDataProvider,
    BrowserInteractionRequired,
)
from src.domain.value_objects.screener_result import MoverData, OrderBookBid, OrderBookTopOfBook


class ManualBrowserDataProvider(BrowserDataProvider):
    """Accepts pre-fetched browser data passed as Python dicts.

    Used when Claude Code (or the user) has already navigated the browser
    and extracted the movers/order-book data.

    Example:
        movers_raw = [{"ticker": "BBCA", "iev": 150000}, ...]
        order_books_raw = {"BBCA": {"price": 8900, "volume": 50000}}

        provider = ManualBrowserDataProvider.from_json(movers_raw, order_books_raw)
    """

    def __init__(
        self,
        movers: list[MoverData],
        order_books: dict[str, OrderBookBid] | None = None,
    ) -> None:
        self._movers = movers
        self._order_books: dict[str, OrderBookBid] = order_books or {}

    @classmethod
    def from_json(
        cls,
        movers_json: list[dict],
        order_books_json: dict[str, dict] | None = None,
    ) -> "ManualBrowserDataProvider":
        """Construct from raw JSON-parsed dicts.

        Args:
            movers_json: List of {"ticker": str, "iev": int, "iep": int | None}
            order_books_json: Map of ticker -> {"price": float, "volume": int}
        """
        movers = [
            MoverData(
                ticker=m["ticker"].upper(),
                iev=int(m["iev"]),
                iep=int(m["iep"]) if m.get("iep") is not None else None,
            )
            for m in movers_json
        ]

        order_books: dict[str, OrderBookBid] = {}
        if order_books_json:
            for ticker, ob in order_books_json.items():
                order_books[ticker.upper()] = OrderBookBid(
                    price=Decimal(str(ob["price"])),
                    volume=int(ob["volume"]),
                )

        return cls(movers=movers, order_books=order_books)

    def fetch_preopen_movers(self, iev_min: int) -> list[MoverData]:
        filtered = [m for m in self._movers if m.iev >= iev_min]
        return sorted(filtered, key=lambda m: m.iev, reverse=True)

    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        return self._order_books.get(ticker.upper())

    def fetch_order_book_top_of_book(self, ticker: str) -> OrderBookTopOfBook | None:
        bid = self.fetch_order_book_best_bid(ticker)
        if bid is None:
            return None
        return OrderBookTopOfBook(bid=bid, offer=None)


class StockbitBrowserInstructionsProvider(BrowserDataProvider):
    """Raises BrowserInteractionRequired with exact Stockbit navigation steps.

    When the CLI has no pre-fetched data, this provider is used. The CLI
    catches the exception and prints the instructions so Claude Code (or
    the user) can perform the browser steps and supply the data via
    --movers-json / --order-books-json flags.
    """

    MOVERS_URL = "https://stockbit.com/#/screener"
    ORDER_BOOK_URL = "https://stockbit.com/#/stock/{ticker}/orderbook"

    def fetch_preopen_movers(self, iev_min: int) -> list[MoverData]:
        raise BrowserInteractionRequired(
            url=self.MOVERS_URL,
            instructions=(
                "1. Open Stockbit and go to the Screener / Movers section\n"
                '2. Click "Selengkapnya" to see all movers\n'
                "3. Sort by IEV column descending (high to low)\n"
                f"4. Collect all rows where IEV >= {iev_min:,}\n"
                "5. Extract ticker and IEV value for each row"
            ),
            data_format='[{"ticker": "BBCA", "iev": 150000}, ...]',
        )

    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        raise BrowserInteractionRequired(
            url=self.ORDER_BOOK_URL.format(ticker=ticker),
            instructions=(
                f"1. Open order book for {ticker} on Stockbit\n"
                "2. Find the largest BID (buy side — highest volume lot)\n"
                "3. Record the price and volume of that bid"
            ),
            data_format='{"price": 8900, "volume": 50000}',
        )
