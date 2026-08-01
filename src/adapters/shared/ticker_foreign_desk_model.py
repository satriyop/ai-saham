"""Ticker foreign-history job desk — design: tui-cockpit-opencode.md §foreign.

Hero · pulses · daily points from real ``ViewTickerForeignHistoryUseCase``.
Point series only (net · lot · avg) — not flow session summaries / top desks.
No fake points, no Action.

Layer: Adapter shared (pure presentation · CLI + TUI)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.view_number_format import format_value


@dataclass(frozen=True)
class ForeignPulse:
    key: str
    label: str
    value: str
    tone: str = "neutral"  # pos | neg | neutral


@dataclass(frozen=True)
class ForeignDayRow:
    date_s: str
    source: str
    net_s: str
    net_tone: str
    lot_s: str
    avg_s: str
    bar_pct: int  # 0–100 relative |net| sugar only


@dataclass(frozen=True)
class TickerForeignDeskModel:
    """Structured foreign-history job surface (not monospaced CLI dump)."""

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
    pulses: tuple[ForeignPulse, ...]
    days: tuple[ForeignDayRow, ...]
    footer: str
    source: str = "—"
    window_days: int = 0
    as_of: str = "—"

    def as_text(self) -> str:
        if self.empty:
            return (
                f"{self.title}\n\nnot cached · foreign flow points empty\nHint: {self.fetch_hint}"
            )
        lines = [
            self.title,
            "",
            f"{self.hero_lab}  {self.hero_big}",
            self.hero_sub,
            "",
            "  ".join(f"{p.label} {p.value}" for p in self.pulses),
            "",
            # of-max % pairs with bar_pct (Scalar bar contract · design §foreign)
            f"{'Date':12}  {'OfMax':>5}  {'Source':10}  {'Net':>12}  {'Lot':>10}  {'Avg':>10}",
            "─" * 66,
        ]
        for d in self.days:
            of_max = f"{max(0, min(100, int(d.bar_pct or 0)))}%"
            lines.append(
                f"{d.date_s:12}  {of_max:>5}  {d.source:10}  {d.net_s:>12}  "
                f"{d.lot_s:>10}  {d.avg_s:>10}"
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


def _date_s(raw: Any) -> str:
    if raw is None:
        return "—"
    if hasattr(raw, "isoformat"):
        return str(raw.isoformat())[:10]
    return str(raw)[:10]


def _window_net(points: Sequence[Any], n: int) -> Decimal | None:
    """Sum net_val over the last n points of a chronological series."""
    if not points or n <= 0:
        return None
    window = list(points)[-n:]
    total = Decimal("0")
    any_ok = False
    for p in window:
        raw = getattr(p, "net_val", None)
        if raw is None:
            continue
        try:
            total += raw if isinstance(raw, Decimal) else Decimal(str(raw))
            any_ok = True
        except Exception:
            continue
    return total if any_ok else None


def build_ticker_foreign_desk_model(
    ticker: str,
    points: Sequence[Any],
    *,
    resolved_source: str = "—",
    window_days: int | None = None,
    as_of: Any = None,
    fetch_hint: str | None = None,
) -> TickerForeignDeskModel:
    """Build foreign desk from real foreign_flow_points window."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch broker-history {ticker_u}"
    title = f"View · ticker · {ticker_u} · foreign-history"
    footer = "esc show · chips switch · CLI · saham view ticker foreign-history · browse only"
    story = "Point series (net · lot · avg).\nNot session summary + top desks (use flow)."

    rows = list(points or ())
    if not rows:
        return TickerForeignDeskModel(
            ticker=ticker_u,
            title=title,
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker foreign-history",
            hero_lab="FOREIGN HISTORY",
            hero_big="—",
            hero_tone="neutral",
            hero_sub=f"not cached · foreign_flow_points empty · Hint: {hint}",
            story=story,
            pulses=(
                ForeignPulse("net5", "5d net", "—"),
                ForeignPulse("net20", "20d net", "—"),
                ForeignPulse("days", "Days", "—"),
                ForeignPulse("src", "Source", "—"),
            ),
            days=(),
            footer=footer,
            source="—",
            window_days=0,
            as_of="—",
        )

    chronological = list(rows)
    try:
        chronological = sorted(
            chronological,
            key=lambda p: getattr(p, "date", None) or "",
        )
    except Exception:
        pass

    n = window_days if window_days is not None else len(chronological)
    latest = chronological[-1]
    latest_net = getattr(latest, "net_val", Decimal("0"))
    as_of_s = _date_s(as_of if as_of is not None else getattr(latest, "date", None))
    src = (resolved_source or getattr(latest, "source", None) or "—").strip() or "—"

    net5 = _window_net(chronological, 5)
    net20 = _window_net(chronological, 20)

    display = list(reversed(chronological))
    abs_nets: list[float] = []
    for p in display:
        try:
            abs_nets.append(abs(float(getattr(p, "net_val", 0) or 0)))
        except (TypeError, ValueError):
            abs_nets.append(0.0)
    max_abs = max(abs_nets) if abs_nets else 0.0

    day_rows: list[ForeignDayRow] = []
    for p in display:
        net = getattr(p, "net_val", Decimal("0"))
        lot = getattr(p, "net_lot", 0)
        avg = getattr(p, "avg_price", None)
        try:
            lot_s = f"{int(lot):,}"
        except (TypeError, ValueError):
            lot_s = str(lot) if lot is not None else "—"
        try:
            avg_s = f"{float(avg):,.0f}" if avg is not None else "—"
        except (TypeError, ValueError):
            avg_s = "—"
        try:
            bar = (
                max(1, min(100, int(round(abs(float(net)) / max_abs * 100)))) if max_abs > 0 else 0
            )
        except (TypeError, ValueError):
            bar = 0
        day_rows.append(
            ForeignDayRow(
                date_s=_date_s(getattr(p, "date", None)),
                source=str(getattr(p, "source", None) or src or "—"),
                net_s=_fmt_signed(net),
                net_tone=_tone_for_signed(net),
                lot_s=lot_s,
                avg_s=avg_s,
                bar_pct=bar,
            )
        )

    hero_big = _fmt_signed(latest_net)
    hero_tone = _tone_for_signed(latest_net)
    hero_sub = (
        f"latest day · source={src} · last {len(chronological)} days · "
        f"foreign net only · as of {as_of_s} · local cache"
    )

    def _pulse_net(key: str, label: str, val: Decimal | None) -> ForeignPulse:
        if val is None:
            return ForeignPulse(key, label, "—")
        return ForeignPulse(key, label, _fmt_signed(val), _tone_for_signed(val))

    pulses = (
        _pulse_net("net5", "5d net", net5),
        _pulse_net("net20", "20d net", net20),
        ForeignPulse("days", "Days", str(len(chronological))),
        ForeignPulse("src", "Source", src),
    )

    return TickerForeignDeskModel(
        ticker=ticker_u,
        title=title,
        empty=False,
        fetch_hint=hint,
        cli_verb="view ticker foreign-history",
        hero_lab="FOREIGN HISTORY",
        hero_big=hero_big,
        hero_tone=hero_tone,
        hero_sub=hero_sub,
        story=story,
        pulses=pulses,
        days=tuple(day_rows),
        footer=footer,
        source=src,
        window_days=int(n),
        as_of=as_of_s,
    )


def empty_ticker_foreign_desk(
    ticker: str, *, message: str = "not cached"
) -> TickerForeignDeskModel:
    ticker_u = str(ticker).upper()
    hint = f"saham fetch broker-history {ticker_u}"
    return TickerForeignDeskModel(
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · foreign-history",
        empty=True,
        fetch_hint=hint,
        cli_verb="view ticker foreign-history",
        hero_lab="FOREIGN HISTORY",
        hero_big="—",
        hero_tone="neutral",
        hero_sub=f"{message} · Hint: {hint}",
        story="Point series (net · lot · avg).\nNot session summary + top desks (use flow).",
        pulses=(
            ForeignPulse("net5", "5d net", "—"),
            ForeignPulse("net20", "20d net", "—"),
            ForeignPulse("days", "Days", "—"),
            ForeignPulse("src", "Source", "—"),
        ),
        days=(),
        footer=("esc show · chips switch · CLI · saham view ticker foreign-history · browse only"),
    )
