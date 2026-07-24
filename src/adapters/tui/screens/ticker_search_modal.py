"""Global `/` ticker search — offline autocomplete over cached tickers.

Opening this modal never queries a provider; results come only from the injected
offline search callable (backed by ``ListCachedTickersUseCase``). A valid
selection returns the chosen ticker to the app, which opens the same workbench
used by the Screen drilldown.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static

SearchTickers = Callable[[str], tuple[str, ...]]


class TickerSearchModal(ModalScreen[str | None]):
    """Prefix search returning a cached ticker, or ``None`` when cancelled."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    # Generous safety bound only: with the current universe (~300 cached tickers)
    # every match is shown and the list scrolls. It exists so a future universe of
    # thousands cannot render an unbounded list on a single keystroke.
    def __init__(self, search_tickers: SearchTickers, *, limit: int = 500) -> None:
        super().__init__()
        self._search = search_tickers
        self._limit = limit
        self._matches: tuple[str, ...] = ()

    def compose(self) -> ComposeResult:
        with Vertical(id="ticker-search-card"):
            yield Static("OPEN TICKER — cached, offline", id="ticker-search-title")
            yield Input(placeholder="Type a ticker prefix…", id="ticker-search-input")
            yield ListView(id="ticker-search-results")
            yield Static("", id="ticker-search-status")

    def on_mount(self) -> None:
        self._refresh_results("")
        self.query_one("#ticker-search-input", Input).focus()

    @on(Input.Changed, "#ticker-search-input")
    def _on_query_changed(self, event: Input.Changed) -> None:
        self._refresh_results(event.value)

    @on(Input.Submitted, "#ticker-search-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        # Enter with a typed exact match opens it directly; otherwise open the
        # first result. Never fabricate a ticker that is not in the catalog.
        typed = event.value.strip().upper()
        if typed and typed in self._matches:
            self.dismiss(typed)
            return
        if self._matches:
            self.dismiss(self._matches[0])

    @on(ListView.Selected, "#ticker-search-results")
    def _on_selected(self, event: ListView.Selected) -> None:
        ticker = getattr(event.item, "ticker", None)
        if ticker:
            self.dismiss(ticker)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _refresh_results(self, prefix: str) -> None:
        available = tuple(self._search(prefix))
        self._matches = available[: self._limit]
        results = self.query_one("#ticker-search-results", ListView)
        results.clear()
        for ticker in self._matches:
            item = ListItem(Static(ticker))
            item.ticker = ticker  # type: ignore[attr-defined]
            results.append(item)
        status = self.query_one("#ticker-search-status", Static)
        if not self._matches:
            status.update("No cached ticker matches.")
        elif len(available) > len(self._matches):
            status.update(
                f"showing {len(self._matches)} of {len(available)} — keep typing to narrow"
            )
        else:
            status.update(f"{len(self._matches)} match(es) — Enter opens, Esc cancels")
