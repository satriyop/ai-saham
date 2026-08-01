"""Ticker brokers job desk — stock desks radar under chip bar (design §brokers).

Same data as ``view ticker top-brokers`` / ticker-desks radar, but **on-ticker**
job shell (not an independent stage). Esc → ticker show · chips switch jobs.

Layer: Adapter shared (pure presentation · CLI + TUI)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BrokersPulse:
    key: str
    label: str
    value: str
    tone: str = "neutral"


@dataclass(frozen=True)
class BrokersDeskRow:
    code: str
    type_label: str
    role: str
    as_of: str
    day_net: str
    net5: str
    streak: str
    delta1: str
    has_partial: bool = False


@dataclass(frozen=True)
class TickerBrokersDeskModel:
    """Structured brokers job · radar facts under ticker chips."""

    ticker: str
    title: str
    empty: bool
    fetch_hint: str
    cli_verb: str
    hero_lab: str
    hero_big: str
    hero_tone: str
    hero_sub: str
    story: str
    pulses: tuple[BrokersPulse, ...]
    rows: tuple[BrokersDeskRow, ...]
    footer: str
    as_of: str = "—"
    note: str = ""
    selected_index: int = 0

    def as_text(self) -> str:
        if self.empty:
            return f"{self.title}\n\nnot cached · no top desks\nHint: {self.fetch_hint}"
        lines = [
            self.title,
            "",
            f"{self.hero_lab}  {self.hero_big}",
            self.hero_sub,
            "",
            "  ".join(f"{p.label} {p.value}" for p in self.pulses),
            "",
            f"{'Code':6} {'Type':8} {'Role':5} {'DayNet':>10} {'Net5':>10} {'Stk':>4} {'Δ1':>10}",
            "─" * 58,
        ]
        for i, r in enumerate(self.rows):
            mark = "›" if i == self.selected_index else " "
            lines.append(
                f"{mark}{r.code:5} {r.type_label:8} {r.role:5} "
                f"{r.day_net:>10} {r.net5:>10} {r.streak:>4} {r.delta1:>10}"
            )
        lines.append("")
        lines.append(self.footer)
        return "\n".join(lines)


def build_ticker_brokers_desk_model(
    ticker: str,
    rows: Sequence[Any],
    *,
    as_of: Any = None,
    note: str | None = None,
    selected_index: int = 0,
    fetch_hint: str | None = None,
) -> TickerBrokersDeskModel:
    """Build brokers job desk from ticker top-desks rows (no invented desks)."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch market {ticker_u}"
    title = f"View · ticker · {ticker_u} · brokers"
    footer = (
        "↑↓ select · Enter desk home · esc show · chips switch · "
        "CLI · saham view ticker top-brokers · browse only"
    )
    story = "Stock desks radar · top brokers for this ticker.\nEnter opens desk home · not Action."
    raw = list(rows or ())
    desk_rows: list[BrokersDeskRow] = []
    for r in raw:
        desk_rows.append(
            BrokersDeskRow(
                code=str(getattr(r, "code", "—") or "—").upper(),
                type_label=str(getattr(r, "type_label", "—") or "—"),
                role=str(getattr(r, "role", "—") or "—"),
                as_of=str(getattr(r, "as_of", "—") or "—")[:10],
                day_net=str(getattr(r, "day_net", "—") or "—"),
                net5=str(getattr(r, "net5", "—") or "—"),
                streak=str(getattr(r, "streak", "—") or "—"),
                delta1=str(getattr(r, "delta1", "—") or "—"),
                has_partial=bool(
                    getattr(r, "has_partial_netx", False) or getattr(r, "partial_net", False)
                ),
            )
        )

    as_of_s = "—"
    if as_of is not None:
        if hasattr(as_of, "isoformat"):
            as_of_s = str(as_of.isoformat())[:10]
        else:
            as_of_s = str(as_of)[:10]
    elif desk_rows:
        as_of_s = desk_rows[0].as_of

    note_s = (note or "").strip()
    n = len(desk_rows)
    sel = max(0, min(int(selected_index), n - 1)) if n else 0
    empty = n == 0

    foreign_n = sum(1 for r in desk_rows if r.type_label.lower().startswith("f"))
    buy_n = sum(1 for r in desk_rows if r.role.lower() == "buy")
    partial_n = sum(1 for r in desk_rows if r.has_partial)

    if empty:
        return TickerBrokersDeskModel(
            ticker=ticker_u,
            title=title,
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker top-brokers",
            hero_lab=f"STOCK DESKS · {ticker_u}",
            hero_big="—",
            hero_tone="neutral",
            hero_sub=f"not cached · no top desks · Hint: {hint}",
            story=story,
            pulses=(
                BrokersPulse("n", "Desks", "—"),
                BrokersPulse("f", "Foreign", "—"),
                BrokersPulse("buy", "Buy role", "—"),
                BrokersPulse("asof", "As of", "—"),
            ),
            rows=(),
            footer=footer,
            as_of=as_of_s,
            note=note_s,
            selected_index=0,
        )

    hero_big = f"{n} desks"
    hero_sub = (
        f"as of {as_of_s} · top brokers · local cache"
        + (f" · {note_s}" if note_s else "")
        + (f" · {partial_n} partial NetX" if partial_n else "")
    )
    pulses = (
        BrokersPulse("n", "Desks", str(n)),
        BrokersPulse("f", "Foreign", str(foreign_n)),
        BrokersPulse("buy", "Buy role", str(buy_n)),
        BrokersPulse("asof", "As of", as_of_s),
    )
    return TickerBrokersDeskModel(
        ticker=ticker_u,
        title=title,
        empty=False,
        fetch_hint=hint,
        cli_verb="view ticker top-brokers",
        hero_lab=f"STOCK DESKS · {ticker_u}",
        hero_big=hero_big,
        hero_tone="neutral",
        hero_sub=hero_sub,
        story=story,
        pulses=pulses,
        rows=tuple(desk_rows),
        footer=footer,
        as_of=as_of_s,
        note=note_s,
        selected_index=sel,
    )
