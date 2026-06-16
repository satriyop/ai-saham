"""
BrowserDataProvider port — interface for browser-sourced market data.

Concrete implementations may scrape a web page, use a headless browser,
or accept data provided externally (e.g., by Claude Code's browser tools).

Layer: Domain
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.screener_result import MoverData, OrderBookBid, OrderBookTopOfBook


class BrowserDataProvider(ABC):
    """Abstract interface for fetching data that requires browser interaction."""

    @abstractmethod
    def fetch_preopen_movers(self, iev_min: int) -> list[MoverData]:
        """Fetch pre-open movers with IEV >= iev_min.

        Args:
            iev_min: Minimum IEV threshold for inclusion

        Returns:
            List of MoverData, sorted by IEV descending

        Raises:
            BrowserInteractionRequired: If a live browser session is needed
            BrowserDataProviderError: On any other fetch failure
        """
        pass

    @abstractmethod
    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        """Fetch the largest bid from the order book for a ticker.

        Args:
            ticker: IDX ticker symbol

        Returns:
            OrderBookBid with price and volume, or None if unavailable

        Raises:
            BrowserInteractionRequired: If a live browser session is needed
            BrowserDataProviderError: On any other fetch failure
        """
        pass

    def fetch_order_book_top_of_book(self, ticker: str) -> OrderBookTopOfBook | None:
        """Fetch best bid and best offer for a ticker.

        Default implementation delegates to fetch_order_book_best_bid() and returns
        offer=None. Override in providers that have offer-side data available.

        Args:
            ticker: IDX ticker symbol

        Returns:
            OrderBookTopOfBook with bid and offer sides, or None if unavailable
        """
        bid = self.fetch_order_book_best_bid(ticker)
        if bid is None:
            return None
        return OrderBookTopOfBook(bid=bid, offer=None)


class BrowserDataProviderError(Exception):
    """Raised when a browser data fetch fails."""

    pass


class BrowserInteractionRequired(BrowserDataProviderError):
    """Raised when the operation requires human/Claude browser interaction.

    The CLI layer catches this and outputs structured instructions so that
    Claude Code (or the user) can navigate the browser and supply the data.

    Attributes:
        url: Target URL to navigate to
        instructions: Human-readable step-by-step browser action instructions
        data_format: Description of the expected return data format (JSON schema)
    """

    def __init__(self, url: str, instructions: str, data_format: str = "") -> None:
        self.url = url
        self.instructions = instructions
        self.data_format = data_format
        super().__init__(f"Browser required: {url}")
