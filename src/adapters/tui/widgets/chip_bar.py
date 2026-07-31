"""Shared Chip bar container (design bible: Shared Chip bar contract).

Plain Tab focus chain via child FlagChip(s). No row labels. Density meta
is optional status text after chips — not a chip.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from src.adapters.tui.widgets.flag_chip import FlagChip

# Ticker show job chips · power b f o x n · density d last (bible §2).
TICKER_JOB_CHIPS: tuple[tuple[str, str], ...] = (
    ("brokers", "brokers"),
    ("flow", "flow"),
    ("foreign", "foreign"),
    ("dist", "dist"),
    ("fin", "fin"),
)
TICKER_JOB_POWER_KEYS: dict[str, str] = {
    "b": "brokers",
    "f": "flow",
    "o": "foreign",
    "x": "dist",
    "n": "fin",
}
# Broker home job chips · power t f c h m
BROKER_HOME_CHIPS: tuple[tuple[str, str], ...] = (
    ("t", "buy/sell"),
    ("f", "flow"),
    ("c", "calendar"),
    ("h", "history"),
    ("m", "top 5"),
)


class ChipBar(Horizontal):
    """Horizontal chip toolbar — children are FlagChip (+ optional meta Static).

    Navigation: mouse click · Tab/Shift+Tab (plain) · Enter/Space on focused chip.
    Power letters live in stage/app handlers (not inside this widget).
    """

    DEFAULT_CSS = """
    ChipBar {
        height: 3;
        width: 100%;
        margin: 0 0 1 0;
        padding: 0;
        align: left middle;
        background: #0b0b0b;
    }
    ChipBar .chip-meta {
        width: auto;
        height: 3;
        color: #6b6b6b;
        padding: 0 0 0 1;
        content-align: left middle;
    }
    """

    def __init__(
        self,
        *,
        id: str | None = None,
        classes: str | None = None,
        chips: Sequence[tuple[str, str]] | None = None,
        chip_id_prefix: str = "chip",
        meta_id: str | None = None,
        meta_text: str = "",
        include_detail: bool = False,
        detail_id: str | None = None,
    ) -> None:
        """Optionally pre-declare chips (compose-time).

        Prefer parent ``compose`` yielding ``ChipBar`` then children, or pass
        ``chips`` / ``include_detail`` for a self-contained bar.
        """
        super().__init__(id=id, classes=classes)
        self._chips_spec: tuple[tuple[str, str], ...] = tuple(chips or ())
        self._chip_id_prefix = chip_id_prefix
        self._meta_id = meta_id
        self._meta_text = meta_text
        self._include_detail = include_detail
        self._detail_id = detail_id or f"{chip_id_prefix}-detail"

    def compose(self) -> ComposeResult:
        for key, label in self._chips_spec:
            yield FlagChip(key, label, id=f"{self._chip_id_prefix}-{key}")
        if self._include_detail:
            yield FlagChip("detail", "detail · d", id=self._detail_id)
        if self._meta_id is not None:
            yield Static(self._meta_text, id=self._meta_id, classes="chip-meta")

    def chip(self, key: str) -> FlagChip | None:
        """Lookup chip by flag_key (scans children)."""
        for child in self.children:
            if isinstance(child, FlagChip) and child.flag_key == key:
                return child
        return None

    def set_meta(self, text: str) -> None:
        if not self._meta_id:
            return
        try:
            self.query_one(f"#{self._meta_id}", Static).update(text)
        except Exception:
            pass

    def paint_states(
        self,
        *,
        on_keys: Iterable[str] = (),
        dim_keys: Iterable[str] = (),
        warn_keys: Iterable[str] = (),
        available_default: bool = True,
    ) -> None:
        """Apply is-on / is-dim / warn to child chips."""
        on = set(on_keys)
        dim = set(dim_keys)
        warn = set(warn_keys)
        for child in self.children:
            if not isinstance(child, FlagChip):
                continue
            key = child.flag_key
            child.set_chip_state(
                available=available_default and key not in dim,
                expanded=key in on,
                warn=key in warn,
            )
