"""Ticker flow job desk model — design: docs/design/tui-cockpit-opencode.md §flow.

Hero · pulses · day table from real ``ViewTickerFlowUseCase`` / BrokerSummary.
No fake nets, no invented top desks, no Action.

Layer: Adapter shared (pure presentation · CLI + TUI)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.view_number_format import format_value


@dataclass(frozen=True)
class FlowPulse:
    key: str
    label: str
    value: str
    tone: str = "neutral"  # pos | neg | neutral


@dataclass(frozen=True)
class FlowDayRow:
    date_s: str
    net_s: str
    net_tone: str
    ratio_s: str
    buyer: str
    seller: str
    bar_pct: int  # 0–100 relative |net| sugar only


@dataclass(frozen=True)
class TickerFlowDeskModel:
    """Structured flow job surface (not monospaced CLI dump)."""

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
    pulses: tuple[FlowPulse, ...]
    days: tuple[FlowDayRow, ...]
    footer: str
    source: str = "—"
    window_days: int = 0
    as_of: str = "—"

    def as_text(self) -> str:
        """Plain text fallback / CLI-parity lines from the same facts."""
        if self.empty:
            return (
                f"{self.title}\n\nnot cached · foreign flow summary empty\nHint: {self.fetch_hint}"
            )
        lines = [
            self.title,
            "",
            f"{self.hero_lab}  {self.hero_big}",
            self.hero_sub,
            "",
            "  ".join(f"{p.label} {p.value}" for p in self.pulses),
            "",
            # of-max % pairs with bar_pct (Scalar bar contract · design §flow)
            f"{'Date':12}  {'OfMax':>5}  {'Net':>12}  {'Ratio':>8}  {'Buyer':>6}  {'Seller':>6}",
            "─" * 60,
        ]
        for d in self.days:
            of_max = f"{max(0, min(100, int(d.bar_pct or 0)))}%"
            lines.append(
                f"{d.date_s:12}  {of_max:>5}  {d.net_s:>12}  {d.ratio_s:>8}  "
                f"{d.buyer:>6}  {d.seller:>6}"
            )
        lines.append("")
        lines.append(self.footer)
        return "\n".join(lines)


def _fmt_signed(value: Decimal | float | int) -> str:
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    s = format_value(d)
    if d > 0 and not s.startswith("+"):
        return f"+{s}"
    return s


def _tone_for_signed(value: Decimal | float | int | None) -> str:
    if value is None:
        return "neutral"
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        return "neutral"
    if d > 0:
        return "pos"
    if d < 0:
        return "neg"
    return "neutral"


def _top_code(side: Any) -> str:
    if not side:
        return "—"
    first = side[0] if isinstance(side, (list, tuple)) else None
    if first is None:
        return "—"
    code = getattr(first, "broker_code", None)
    if code is None and isinstance(first, dict):
        code = first.get("broker_code")
    s = str(code or "").strip()
    return s if s else "—"


def _date_s(raw: Any) -> str:
    if raw is None:
        return "—"
    if hasattr(raw, "isoformat"):
        return str(raw.isoformat())[:10]
    return str(raw)[:10]


def build_ticker_flow_desk_model(
    ticker: str,
    summaries: Sequence[Any],
    *,
    total_net: Decimal | None = None,
    buy_days: int | None = None,
    sell_days: int | None = None,
    window_days: int | None = None,
    source: str | None = None,
    as_of: Any = None,
    fetch_hint: str | None = None,
) -> TickerFlowDeskModel:
    """Build flow desk from real broker_summaries window (no invented rows)."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch market {ticker_u}"
    title = f"View · ticker · {ticker_u} · flow"
    footer = "esc show · chips switch · CLI · saham view ticker flow · browse only"

    rows = list(summaries or ())
    if not rows:
        return TickerFlowDeskModel(
            ticker=ticker_u,
            title=title,
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker flow",
            hero_lab="FOREIGN FLOW",
            hero_big="—",
            hero_tone="neutral",
            hero_sub=f"not cached · broker_summaries empty · Hint: {hint}",
            story="Window net foreign on this stock.\nNot the point series (use foreign).",
            pulses=(
                FlowPulse("buy", "Buy days", "—"),
                FlowPulse("sell", "Sell days", "—"),
                FlowPulse("consec", "Consec buy", "—"),
                FlowPulse("latest", "Latest", "—"),
            ),
            days=(),
            footer=footer,
            source="—",
            window_days=0,
            as_of="—",
        )

    n = window_days if window_days is not None else len(rows)
    total = total_net
    if total is None:
        total = sum(
            (getattr(s, "foreign_net_value", Decimal("0")) for s in rows),
            Decimal("0"),
        )
    buys = buy_days
    if buys is None:
        buys = sum(1 for s in rows if getattr(s, "is_foreign_accumulating", False))
    sells = sell_days if sell_days is not None else max(0, len(rows) - int(buys))

    # Consecutive buy from newest session backward
    chronological = list(rows)
    try:
        chronological = sorted(
            chronological,
            key=lambda s: getattr(s, "date", None) or "",
        )
    except Exception:
        pass
    consecutive = 0
    for s in reversed(chronological):
        if getattr(s, "is_foreign_accumulating", False):
            consecutive += 1
        else:
            break

    latest = chronological[-1]
    latest_net = getattr(latest, "foreign_net_value", Decimal("0"))
    as_of_s = _date_s(as_of if as_of is not None else getattr(latest, "date", None))
    src = (source or getattr(latest, "source", None) or "cache").strip() or "cache"

    # Day rows: newest first for desk scan
    display = list(reversed(chronological))
    abs_nets: list[float] = []
    for s in display:
        try:
            abs_nets.append(abs(float(getattr(s, "foreign_net_value", 0) or 0)))
        except (TypeError, ValueError):
            abs_nets.append(0.0)
    max_abs = max(abs_nets) if abs_nets else 0.0

    day_rows: list[FlowDayRow] = []
    for s in display:
        net = getattr(s, "foreign_net_value", Decimal("0"))
        ratio = getattr(s, "foreign_flow_ratio", Decimal("0"))
        try:
            ratio_f = float(ratio)
            ratio_s = f"{ratio_f:.1f}%"
        except (TypeError, ValueError):
            ratio_s = "—"
        try:
            bar = (
                max(1, min(100, int(round(abs(float(net)) / max_abs * 100)))) if max_abs > 0 else 0
            )
        except (TypeError, ValueError):
            bar = 0
        day_rows.append(
            FlowDayRow(
                date_s=_date_s(getattr(s, "date", None)),
                net_s=_fmt_signed(net),
                net_tone=_tone_for_signed(net),
                ratio_s=ratio_s,
                buyer=_top_code(getattr(s, "top_buyers", None) or ()),
                seller=_top_code(getattr(s, "top_sellers", None) or ()),
                bar_pct=bar,
            )
        )

    hero_big = _fmt_signed(total)
    hero_tone = _tone_for_signed(total)
    hero_lab = f"FOREIGN FLOW · {n}d"
    hero_sub = (
        f"last {len(rows)} sessions · broker_summaries · as of {as_of_s} · "
        f"source={src} · local cache"
    )

    pulses = (
        FlowPulse("buy", "Buy days", str(int(buys))),
        FlowPulse("sell", "Sell days", str(int(sells))),
        FlowPulse("consec", "Consec buy", str(int(consecutive))),
        FlowPulse(
            "latest",
            "Latest",
            _fmt_signed(latest_net),
            _tone_for_signed(latest_net),
        ),
    )

    return TickerFlowDeskModel(
        ticker=ticker_u,
        title=title,
        empty=False,
        fetch_hint=hint,
        cli_verb="view ticker flow",
        hero_lab=hero_lab,
        hero_big=hero_big,
        hero_tone=hero_tone,
        hero_sub=hero_sub,
        story="Window net foreign on this stock.\nNot the point series (use foreign).",
        pulses=pulses,
        days=tuple(day_rows),
        footer=footer,
        source=src,
        window_days=int(n),
        as_of=as_of_s,
    )


def empty_ticker_flow_desk(ticker: str, *, message: str = "not cached") -> TickerFlowDeskModel:
    ticker_u = str(ticker).upper()
    hint = f"saham fetch market {ticker_u}"
    return TickerFlowDeskModel(
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · flow",
        empty=True,
        fetch_hint=hint,
        cli_verb="view ticker flow",
        hero_lab="FOREIGN FLOW",
        hero_big="—",
        hero_tone="neutral",
        hero_sub=f"{message} · Hint: {hint}",
        story="Window net foreign on this stock.\nNot the point series (use foreign).",
        pulses=(
            FlowPulse("buy", "Buy days", "—"),
            FlowPulse("sell", "Sell days", "—"),
            FlowPulse("consec", "Consec buy", "—"),
            FlowPulse("latest", "Latest", "—"),
        ),
        days=(),
        footer="esc show · chips switch · CLI · saham view ticker flow · browse only",
    )
