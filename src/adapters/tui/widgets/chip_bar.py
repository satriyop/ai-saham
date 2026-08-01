"""Shared Chip bar container (design bible: Shared Chip bar contract).

Plain Tab focus chain via child FlagChip(s). No row labels.
Density state = ``[d] detail`` chip ``is-on`` only — no brief/detail meta text.
Job chips paint bold brass ``[k]`` keycaps (power letters).
Binary toggles (e.g. fin period ``[y]``) use real bindings only — never decoration.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from textual.app import ComposeResult
from textual.containers import Horizontal

from src.adapters.tui.widgets.flag_chip import FlagChip

# Ticker show job chips · power b f o x n · density d last (bible §2).
# Fin period grain is not a job: binary toggle [y] between fin and detail.
# (flag_key, product_word)
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
# Job-local binary toggle · fin period grain (not a job power key)
TICKER_FIN_PERIOD_FLAG = "period"
TICKER_FIN_PERIOD_POWER = "y"
# flag_key → power letter (inverse of TICKER_JOB_POWER_KEYS)
TICKER_JOB_FLAG_POWER: dict[str, str] = {v: k for k, v in TICKER_JOB_POWER_KEYS.items()}
# Broker home job chips · power t f c h m · (flag_key == power letter)
BROKER_HOME_CHIPS: tuple[tuple[str, str], ...] = (
    ("t", "buy/sell"),
    ("f", "flow"),
    ("c", "calendar"),
    ("h", "history"),
    ("m", "top 5"),
)


def power_key_for_flag(flag_key: str) -> str | None:
    """Resolve power letter for a chip flag_key (ticker / broker / density / period)."""
    k = (flag_key or "").strip()
    if not k:
        return None
    if k == "detail":
        return "d"
    if k == TICKER_FIN_PERIOD_FLAG:
        return TICKER_FIN_PERIOD_POWER
    if k in TICKER_JOB_FLAG_POWER:
        return TICKER_JOB_FLAG_POWER[k]
    # Broker home: flag_key is the letter
    if len(k) == 1 and k.isalpha():
        return k.lower()
    return None


class ChipBar(Horizontal):
    """Horizontal chip toolbar — children are FlagChip.

    Navigation: mouse click · Tab/Shift+Tab (plain) · Enter/Space on focused chip.
    Power letters live in stage/app handlers (not inside this widget); chips paint
    the same letters as brass ``[k]`` keycaps.
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
        include_fin_period: bool = False,
        period_id: str | None = None,
    ) -> None:
        """Optionally pre-declare chips (compose-time).

        Prefer parent ``compose`` yielding ``ChipBar`` then children, or pass
        ``chips`` / ``include_detail`` for a self-contained bar.

        ``include_fin_period``: job-local binary toggle ``[y] quarterly|annual``
        between jobs and density. **Paint/show only while fin is front** — hidden
        (not dimmed) on show and other jobs; parent sets ``display`` / unbinds ``y``.

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
        self._include_fin_period = include_fin_period
        self._period_id = period_id or f"{chip_id_prefix}-period"

    def compose(self) -> ComposeResult:
        for flag_key, word in self._chips_spec:
            yield FlagChip(
                flag_key,
                word,
                power_key=power_key_for_flag(flag_key),
                id=f"{self._chip_id_prefix}-{flag_key}",
            )
        if self._include_fin_period:
            # Binary toggle · flip label · power y · not a job.
            # Starts context-off (hidden) — parent arms only while fin is-on.
            yield FlagChip(
                TICKER_FIN_PERIOD_FLAG,
                "quarterly",
                power_key=TICKER_FIN_PERIOD_POWER,
                id=self._period_id,
                classes="is-context-off",
            )
        if self._include_detail:
            # Design lock: [d] detail · is-on = detail · no brief meta
            yield FlagChip(
                "detail",
                "detail",
                power_key="d",
                id=self._detail_id,
            )

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
        skip_keys: Iterable[str] = (),
    ) -> None:
        """Apply is-on / is-dim / warn to child chips.

        ``skip_keys``: leave those chips alone (e.g. context-off fin period).
        """
        on = set(on_keys)
        dim = set(dim_keys)
        warn = set(warn_keys)
        skip = set(skip_keys)
        for child in self.children:
            if not isinstance(child, FlagChip):
                continue
            key = child.flag_key
            if key in skip or child.has_class("is-context-off"):
                continue
            child.set_chip_state(
                available=available_default and key not in dim,
                expanded=key in on,
                warn=key in warn,
            )
