"""Ticker brokers job desk — stock desks radar under chip bar (design §brokers).

Same data as ``view ticker top-brokers`` / ticker-desks radar, but **on-ticker**
job shell (not an independent stage). Esc → ticker show · chips switch jobs.

Radar columns: DayNet · Net3/5/7/10/20 · Stk · Δ1.
No implementer noise in hero sub (no tops_scope_note essays).

Layer: Adapter shared (pure presentation · CLI + TUI)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Match STOCK_DESK_NET_WINDOWS / ticker-desks radar
_NET_WINDOWS: tuple[int, ...] = (3, 5, 7, 10, 20)


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
    net3: str
    net5: str
    net7: str
    net10: str
    net20: str
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
            "",
            # Design cockpit labels (Code · Type · Role · DayNet · Net3… · Stk · Δ1)
            f"{'Code':5} {'Type':8} {'Role':4} {'DayNet':>8} "
            f"{'Net3':>8} {'Net5':>8} {'Net7':>8} {'Net10':>8} {'Net20':>8} "
            f"{'Stk':>3} {'Δ1':>8}",
            "─" * 80,
        ]
        for i, r in enumerate(self.rows):
            mark = "›" if i == self.selected_index else " "
            role = (r.role or "—").strip().lower()
            if role.startswith("buy"):
                role_s = "buy"
            elif role.startswith("sell"):
                role_s = "sell"
            else:
                role_s = (r.role or "—")[:4]
            lines.append(
                f"{mark}{r.code:4} {r.type_label[:8]:8} {role_s:4} "
                f"{r.day_net:>8} {r.net3:>8} {r.net5:>8} {r.net7:>8} "
                f"{r.net10:>8} {r.net20:>8} {r.streak:>3} {r.delta1:>8}"
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
    footer = "↑↓ · Enter desk · esc show · chips switch · browse only"
    # Empty story — no essay under radar (design: reject noise)
    story = ""
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
                net3=str(getattr(r, "net3", "—") or "—"),
                net5=str(getattr(r, "net5", "—") or "—"),
                net7=str(getattr(r, "net7", "—") or "—"),
                net10=str(getattr(r, "net10", "—") or "—"),
                net20=str(getattr(r, "net20", "—") or "—"),
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

    # Keep note only for internal/meta callers — never paint as hero essay
    note_s = (note or "").strip()
    n = len(desk_rows)
    sel = max(0, min(int(selected_index), n - 1)) if n else 0
    empty = n == 0

    foreign_n = sum(1 for r in desk_rows if r.type_label.lower().startswith("f"))
    buy_n = sum(1 for r in desk_rows if r.role.lower() == "buy")

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
            hero_sub=f"Hint: {hint}",
            story=story,
            pulses=(
                BrokersPulse("n", "Desks", "—"),
                BrokersPulse("f", "Foreign", "—"),
                BrokersPulse("buy", "Buy", "—"),
                BrokersPulse("asof", "As of", "—"),
            ),
            rows=(),
            footer=footer,
            as_of=as_of_s,
            note=note_s,
            selected_index=0,
        )

    # Hero: lab + N desks only — no tops_scope_note / Net window essay (noise)
    hero_big = f"{n} desks"
    hero_sub = ""
    pulses = (
        BrokersPulse("n", "Desks", str(n)),
        BrokersPulse("f", "Foreign", str(foreign_n)),
        BrokersPulse("buy", "Buy", str(buy_n)),
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
