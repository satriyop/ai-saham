"""Shared Chip bar container (design bible: Shared Chip bar contract).

Plain Tab focus chain via child FlagChip(s). No row labels.
Density state = ``[d] detail`` chip ``is-on`` only — no brief/detail meta text.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from textual.app import ComposeResult
from textual.containers import Horizontal

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
        /* Legacy hook — density status text is forbidden (display off) */
        display: none;
        width: 0;
        height: 0;
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

        ``meta_id`` / ``meta_text`` are accepted for call-site compatibility but
        **not painted** — density state is chip ``is-on`` only (design lock).
        """
        super().__init__(id=id, classes=classes)
        self._chips_spec: tuple[tuple[str, str], ...] = tuple(chips or ())
        self._chip_id_prefix = chip_id_prefix
        self._meta_id = meta_id
        self._meta_text = meta_text  # ignored for density (no brief/detail meta)
        self._include_detail = include_detail
        self._detail_id = detail_id or f"{chip_id_prefix}-detail"

    def compose(self) -> ComposeResult:
        for key, label in self._chips_spec:
            yield FlagChip(key, label, id=f"{self._chip_id_prefix}-{key}")
        if self._include_detail:
            # Design lock: [d] detail · is-on = detail · no brief meta
            yield FlagChip("detail", "[d] detail", id=self._detail_id)

    def chip(self, key: str) -> FlagChip | None:
        """Lookup chip by flag_key (scans children)."""
        for child in self.children:
            if isinstance(child, FlagChip) and child.flag_key == key:
                return child
        return None

    def set_meta(self, text: str) -> None:
        """No-op: density/job meta text removed (chip is-on is the state)."""
        return

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
