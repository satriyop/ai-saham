"""Ticker distribution job desk — design: tui-cockpit-opencode.md §dist.

Hero · pulses · dual heat (buyers / sellers) from real
``ViewTickerDistributionUseCase`` / BrokerDistributionSnapshot.
Type tags: F = Foreign · L = Local · G = government — never A (Asing).
No fake sides, no Action.

Layer: Adapter shared (pure presentation · CLI + TUI)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DistPulse:
    key: str
    label: str
    value: str
    tone: str = "neutral"  # pos | neg | neutral


@dataclass(frozen=True)
class DistCpRow:
    code: str
    type_tag: str  # F | L | G
    amount_s: str
    pct: int  # 0–100 of parent side amount
    bar_pct: int


@dataclass(frozen=True)
class DistSideRow:
    rank: int
    code: str
    type_tag: str
    amount_s: str
    cps: tuple[DistCpRow, ...]


@dataclass(frozen=True)
class TickerDistDeskModel:
    """Structured distribution job surface (not monospaced CLI dump)."""

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
    pulses: tuple[DistPulse, ...]
    buyers: tuple[DistSideRow, ...]
    sellers: tuple[DistSideRow, ...]
    footer: str
    as_of: str = "—"
    source: str = "—"
    slogan: str = ""  # empty when not true

    def as_text(self) -> str:
        if self.empty:
            return (
                f"{self.title}\n\nnot cached · broker distribution empty\nHint: {self.fetch_hint}"
            )
        lines = [
            self.title,
            "",
            f"{self.hero_lab}  {self.hero_big}",
            self.hero_sub,
            "",
            "  ".join(f"{p.label} {p.value}" for p in self.pulses),
            "",
        ]
        if self.buyers:
            lines.append("TOP BUYERS  (bought FROM →)")
            for s in self.buyers:
                lines.append(f"  {s.rank} {s.code}[{s.type_tag}]  {s.amount_s}")
                for cp in s.cps:
                    lines.append(f"    ← {cp.code}[{cp.type_tag}]  {cp.amount_s}  ({cp.pct}%)")
            lines.append("")
        if self.sellers:
            lines.append("TOP SELLERS (sold TO →)")
            for s in self.sellers:
                lines.append(f"  {s.rank} {s.code}[{s.type_tag}]  {s.amount_s}")
                for cp in s.cps:
                    lines.append(f"    → {cp.code}[{cp.type_tag}]  {cp.amount_s}  ({cp.pct}%)")
            lines.append("")
        lines.append(self.footer)
        return "\n".join(lines)


def type_tag(broker_type: str | None) -> str:
    """F = Foreign · L = Local · G = government — never A (Asing)."""
    t = (broker_type or "").lower().strip()
    if t in {"asing", "foreign", "f"}:
        return "F"
    if t in {"pemerintah", "government", "g"}:
        return "G"
    return "L"


def _fmt_idr_amount(amount: int | float) -> str:
    try:
        amt = int(amount)
    except (TypeError, ValueError):
        return "—"
    abs_amt = abs(amt)
    if abs_amt >= 1_000_000_000_000:
        return f"{amt / 1_000_000_000_000:.1f}T"
    if abs_amt >= 1_000_000_000:
        return f"{amt / 1_000_000_000:.1f}B"
    if abs_amt >= 1_000_000:
        return f"{amt / 1_000_000:.1f}M"
    return f"{amt:,}"


def _date_s(raw: Any) -> str:
    if raw is None:
        return "—"
    if hasattr(raw, "isoformat"):
        return str(raw.isoformat())[:10]
    return str(raw)[:10]


def _side_rows(
    entries: Sequence[Any],
    *,
    max_sides: int = 5,
    max_cps: int = 4,
) -> list[DistSideRow]:
    out: list[DistSideRow] = []
    for i, entry in enumerate(list(entries or ())[:max_sides], start=1):
        code = str(getattr(entry, "broker_code", "—") or "—")
        tag = type_tag(str(getattr(entry, "broker_type", "") or ""))
        try:
            amt = int(getattr(entry, "amount_idr", 0) or 0)
        except (TypeError, ValueError):
            amt = 0
        cps: list[DistCpRow] = []
        for cp in list(getattr(entry, "counterparties", ()) or ())[:max_cps]:
            try:
                cp_amt = int(getattr(cp, "amount_idr", 0) or 0)
            except (TypeError, ValueError):
                cp_amt = 0
            pct = int(round(cp_amt / amt * 100)) if amt else 0
            pct = max(0, min(100, pct))
            cps.append(
                DistCpRow(
                    code=str(getattr(cp, "broker_code", "—") or "—"),
                    type_tag=type_tag(str(getattr(cp, "broker_type", "") or "")),
                    amount_s=_fmt_idr_amount(cp_amt),
                    pct=pct,
                    bar_pct=max(1, pct) if pct > 0 else 0,
                )
            )
        out.append(
            DistSideRow(
                rank=i,
                code=code,
                type_tag=tag,
                amount_s=_fmt_idr_amount(amt),
                cps=tuple(cps),
            )
        )
    return out


def build_ticker_dist_desk_model(
    ticker: str,
    snapshot: Any | None,
    *,
    as_of: Any = None,
    source: str | None = None,
    fetch_hint: str | None = None,
) -> TickerDistDeskModel:
    """Build dist desk from real BrokerDistributionSnapshot (no invented sides)."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch market {ticker_u}"
    title = f"View · ticker · {ticker_u} · distribution"
    footer = "esc show · chips switch · CLI · saham view ticker distribution · browse only"
    story = (
        "Counterparty matrix · F=Foreign L=Local · never A.\n"
        "Not foreign history points (use foreign)."
    )

    if snapshot is None:
        return TickerDistDeskModel(
            ticker=ticker_u,
            title=title,
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker distribution",
            hero_lab=f"DISTRIBUTION · {ticker_u}",
            hero_big="—",
            hero_tone="neutral",
            hero_sub=f"not cached · distribution empty · Hint: {hint}",
            story=story,
            pulses=(
                DistPulse("buy_n", "Buy sides", "—"),
                DistPulse("sell_n", "Sell sides", "—"),
                DistPulse("top_b", "Top buy", "—"),
                DistPulse("top_s", "Top sell", "—"),
            ),
            buyers=(),
            sellers=(),
            footer=footer,
            as_of="—",
            source="—",
            slogan="",
        )

    buyers = _side_rows(getattr(snapshot, "top_buyers", ()) or ())
    sellers = _side_rows(getattr(snapshot, "top_sellers", ()) or ())
    empty = not buyers and not sellers

    as_of_s = _date_s(as_of if as_of is not None else getattr(snapshot, "date", None))
    src = (source or "broker_distribution_cache").strip() or "cache"

    slogan = ""
    hero_tone = "neutral"
    if getattr(snapshot, "foreign_buying_from_domestic", False):
        slogan = "★ Foreign buying from domestic"
        hero_tone = "pos"
    elif getattr(snapshot, "net_foreign_buyer_dominance", False):
        slogan = "● Foreign dominate buys"
        hero_tone = "pos"

    hero_big = slogan if slogan else "counterparty matrix"
    if empty:
        hero_big = "—"
        hero_tone = "neutral"

    top_b = f"{buyers[0].code} · {buyers[0].amount_s}" if buyers else "—"
    top_s = f"{sellers[0].code} · {sellers[0].amount_s}" if sellers else "—"

    pulses = (
        DistPulse("buy_n", "Buy sides", str(len(buyers))),
        DistPulse("sell_n", "Sell sides", str(len(sellers))),
        DistPulse("top_b", "Top buy", top_b, "pos" if buyers else "neutral"),
        DistPulse("top_s", "Top sell", top_s, "neg" if sellers else "neutral"),
    )

    return TickerDistDeskModel(
        ticker=ticker_u,
        title=title,
        empty=empty,
        fetch_hint=hint,
        cli_verb="view ticker distribution",
        hero_lab=f"DISTRIBUTION · {ticker_u}",
        hero_big=hero_big,
        hero_tone=hero_tone,
        hero_sub=(f"as of {as_of_s} · counterparty · source={src} · local cache · not Action"),
        story=story,
        pulses=pulses,
        buyers=tuple(buyers),
        sellers=tuple(sellers),
        footer=footer,
        as_of=as_of_s,
        source=src,
        slogan=slogan,
    )


def empty_ticker_dist_desk(ticker: str, *, message: str = "not cached") -> TickerDistDeskModel:
    ticker_u = str(ticker).upper()
    hint = f"saham fetch market {ticker_u}"
    return TickerDistDeskModel(
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · distribution",
        empty=True,
        fetch_hint=hint,
        cli_verb="view ticker distribution",
        hero_lab=f"DISTRIBUTION · {ticker_u}",
        hero_big="—",
        hero_tone="neutral",
        hero_sub=f"{message} · Hint: {hint}",
        story="Counterparty matrix · F=Foreign L=Local · never A.",
        pulses=(
            DistPulse("buy_n", "Buy sides", "—"),
            DistPulse("sell_n", "Sell sides", "—"),
            DistPulse("top_b", "Top buy", "—"),
            DistPulse("top_s", "Top sell", "—"),
        ),
        buyers=(),
        sellers=(),
        footer=("esc show · chips switch · CLI · saham view ticker distribution · browse only"),
        slogan="",
    )
