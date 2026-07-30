"""Ticker desk model — design: docs/design/tui-ticker-desk.html (Harga Mast).

Hierarchy (design adopt list):
  identity → monumental price + horizons → metric ribbon → pulse trio
  → earnings → secondary kv · never CLI dump as primary surface.

Cache dashboard only — never Action.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TickerMetric:
    label: str
    value: str
    unit: str = ""


@dataclass(frozen=True)
class TickerHorizon:
    label: str
    value: str
    tone: str = "neutral"  # pos | neg | neutral
    bar_pct: int = 0  # 0–100 visual density only


@dataclass(frozen=True)
class PulseCard:
    """One of flow / structure / bandar pulse cards."""

    key: str
    title: str
    headline: str
    sub: str
    rows: tuple[tuple[str, str], ...]  # (k, v)
    tone: str = "neutral"  # pos | neg | neutral


@dataclass(frozen=True)
class EarnRow:
    period: str
    eps: str
    yoy: str
    yoy_tone: str = "neutral"
    bar_pct: int = 50


@dataclass(frozen=True)
class TickerDeskModel:
    ticker: str
    name: str
    board: str
    sector: str
    tradeable: str
    price: str
    change_1d: str
    change_tone: str
    as_of: str
    horizons: tuple[TickerHorizon, ...]
    metrics: tuple[TickerMetric, ...]
    freshness: tuple[str, ...]
    pulses: tuple[PulseCard, ...]
    earnings: tuple[EarnRow, ...]
    secondary: tuple[tuple[str, str], ...]
    authority: str
    footer: str
    # Optional raw body for scrapers only — not painted as primary stage.
    body: str = ""

    def as_text(self) -> str:
        lines = [
            f"View · ticker desk · {self.ticker}",
            f"{self.name} · {self.board} · {self.sector}",
            "HARGA MAST",
            f"Rp {self.price}  {self.change_1d}".strip(),
            f"as_of {self.as_of} · {self.authority}",
        ]
        for p in self.pulses:
            lines.append(f"{p.title}: {p.headline} · {p.sub}")
        for e in self.earnings[:4]:
            lines.append(f"{e.period}  eps {e.eps}  yoy {e.yoy}")
        return "\n".join(lines)


def build_ticker_desk_model_from_dashboard(
    dashboard: Any,
    *,
    body: str = "",
) -> TickerDeskModel:
    """Build design hierarchy from GetTickerDashboardUseCase result."""
    ticker = str(getattr(dashboard, "ticker", "?") or "?").upper()
    price = _fmt_price(getattr(dashboard, "latest_close", None))
    as_of = getattr(dashboard, "as_of", None)
    as_of_s = str(as_of)[:10] if as_of is not None else "—"

    name, board, sector, tradeable = _identity(dashboard)
    ps = getattr(dashboard, "price_structure", None)
    change_1d, change_tone = "—", "neutral"
    horizons: list[TickerHorizon] = []
    if ps is not None:
        change_1d, change_tone = _fmt_pct(getattr(ps, "change_1d_pct", None))
        if change_1d != "—":
            change_1d = f"{change_1d} 1d"
        horizons = _horizons_from_ps(ps)
    else:
        horizons = _empty_horizons()

    metrics = _metrics_from_fund(getattr(dashboard, "fundamentals", None))
    freshness = _freshness_pills(getattr(dashboard, "freshness", None) or ())
    pulses = (
        _pulse_flow(dashboard),
        _pulse_structure(ps),
        _pulse_bandar(getattr(dashboard, "bandar", None)),
    )
    earnings = _earnings_rows(getattr(dashboard, "earnings", None) or ())
    secondary = _secondary_kv(dashboard)

    return TickerDeskModel(
        ticker=ticker,
        name=name,
        board=board,
        sector=sector,
        tradeable=tradeable,
        price=price,
        change_1d=change_1d if change_1d != "—" else "",
        change_tone=change_tone,
        as_of=as_of_s,
        horizons=tuple(horizons),
        metrics=tuple(metrics),
        freshness=tuple(freshness),
        pulses=pulses,
        earnings=tuple(earnings),
        secondary=tuple(secondary),
        authority="cache dashboard · not Action",
        footer="b desks · p plan · esc board · CLI deep-dives stay CLI · no order · no re-score",
        body=(body or "").strip(),
    )


def build_ticker_desk_model_from_text(*, ticker: str, body: str) -> TickerDeskModel:
    """Minimal model when only text is available (stub loaders / tests)."""
    import re

    price = "—"
    for pat in (
        r"(?:Close|Last|Price|Harga)\s*[:=]?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)",
        r"\b([0-9]{1,3}(?:,[0-9]{3})+)\b",
    ):
        m = re.search(pat, body or "", re.I)
        if m:
            price = m.group(1)
            break
    return TickerDeskModel(
        ticker=str(ticker or "?").upper(),
        name="—",
        board="—",
        sector="—",
        tradeable="—",
        price=price,
        change_1d="",
        change_tone="neutral",
        as_of="—",
        horizons=_empty_horizons(),
        metrics=_empty_metrics(),
        freshness=(),
        pulses=(
            PulseCard("flow", "Foreign flow", "—", "no flow series", (), "neutral"),
            PulseCard("struct", "Structure", "—", "no structure", (), "neutral"),
            PulseCard("bandar", "Bandar", "—", "no bandar", (), "neutral"),
        ),
        earnings=(),
        secondary=(("Depth", "text-only stub · full panels need live dashboard"),),
        authority="cache dashboard · not Action",
        footer="b desks · p plan · esc board · no order · no re-score",
        body=(body or "").strip(),
    )


# ── builders ───────────────────────────────────────────────


def _identity(dashboard: Any) -> tuple[str, str, str, str]:
    name, board, sector, tradeable = "—", "—", "—", "—"
    notation = getattr(dashboard, "notation", None)
    if notation is not None:
        board = str(getattr(notation, "listing_board", None) or board)
        sector = str(getattr(notation, "sector", None) or sector)
        sub = getattr(notation, "sub_sector", None)
        if sub and sector != "—":
            sector = f"{sector} · {sub}"
        elif sub:
            sector = str(sub)
        t = getattr(notation, "tradeable", None)
        if t is True:
            tradeable = "Tradeable"
        elif t is False:
            tradeable = "Not tradeable"
        ns = getattr(notation, "notations", None) or ()
        if ns:
            name = str(getattr(ns[0], "description", None) or "—")
        else:
            name = str(getattr(notation, "description", None) or name)
    profile = getattr(dashboard, "profile", None)
    if profile is not None:
        if board == "—":
            board = str(getattr(profile, "listing_board", None) or "—")
        if name == "—":
            name = str(
                getattr(profile, "name", None) or getattr(profile, "company_name", None) or "—"
            )
    return name, board, sector, tradeable


def _horizons_from_ps(ps: Any) -> list[TickerHorizon]:
    out: list[TickerHorizon] = []
    for lab, attr, is_range in (
        ("1d", "change_1d_pct", False),
        ("5d", "change_5d_pct", False),
        ("20d", "change_20d_pct", False),
        ("52w", "range_52w_pct", True),
    ):
        raw = getattr(ps, attr, None)
        if is_range and raw is not None:
            try:
                v = float(raw)
                out.append(TickerHorizon(lab, f"{v:.0f}%", "neutral", _bar_from_abs(v, 100)))
            except (TypeError, ValueError):
                out.append(TickerHorizon(lab, "—", "neutral", 0))
            continue
        val, tone = _fmt_pct(raw)
        bar = 0
        if raw is not None:
            try:
                bar = _bar_from_abs(float(raw), 20.0)
            except (TypeError, ValueError):
                bar = 30
        out.append(TickerHorizon(lab, val, tone, bar))
    return out


def _empty_horizons() -> tuple[TickerHorizon, ...]:
    return tuple(TickerHorizon(x, "—", "neutral", 0) for x in ("1d", "5d", "20d", "52w"))


def _metrics_from_fund(fund: Any) -> list[TickerMetric]:
    if fund is None:
        return list(_empty_metrics())
    return [
        TickerMetric("PE TTM", _fmt_num(getattr(fund, "pe_ratio_ttm", None))),
        TickerMetric("PBV", _fmt_num(getattr(fund, "pbv", None))),
        TickerMetric("MCap", _fmt_mcap(getattr(fund, "market_cap_idr", None)), "IDR"),
        TickerMetric("ROE", _fmt_pct_value(getattr(fund, "roe_ttm", None))),
        TickerMetric("Div yield", _fmt_pct_value(getattr(fund, "dividend_yield", None))),
        TickerMetric("F-Score", _fmt_int(getattr(fund, "piotroski_f_score", None))),
    ]


def _empty_metrics() -> tuple[TickerMetric, ...]:
    return (
        TickerMetric("PE TTM", "—"),
        TickerMetric("PBV", "—"),
        TickerMetric("MCap", "—", "IDR"),
        TickerMetric("ROE", "—"),
        TickerMetric("Div yield", "—"),
        TickerMetric("F-Score", "—"),
    )


def _freshness_pills(items: Any) -> list[str]:
    out: list[str] = []
    for item in list(items)[:10]:
        label = str(getattr(item, "label", None) or getattr(item, "key", "?") or "?")
        st = getattr(item, "status", None)
        st_s = str(getattr(st, "value", st) or "").lower()
        if st_s == "ok":
            out.append(f"✓{label}")
        elif st_s in {"missing", "empty", "error"}:
            out.append(f"✗{label}")
        elif st_s == "stale":
            out.append(f"~{label}")
        else:
            out.append(label)
    return out


def _pulse_flow(dashboard: Any) -> PulseCard:
    points = list(getattr(dashboard, "foreign_flow_points", None) or ())
    source = str(getattr(dashboard, "foreign_flow_source", None) or "cache")
    if not points:
        return PulseCard(
            "flow",
            "Foreign flow",
            "—",
            "no foreign flow series · local cache",
            (("Latest", "—"), ("5d net", "—"), ("20d net", "—"), ("Source", source)),
            "neutral",
        )
    latest = points[-1]
    latest_net = getattr(latest, "net_val", None)
    latest_s, tone = _fmt_idr(latest_net)
    net5, t5 = _window_net(points, 5)
    net20, t20 = _window_net(points, 20)
    buy5, sell5 = _window_buy_sell(points, 5)
    head = net5 if net5 != "—" else latest_s
    head_tone = t5 if net5 != "—" else tone
    sub = f"5d net · {source}"
    if buy5 is not None:
        sub = f"5d net · {source} · {buy5} buy / {sell5} sell"
    sess = str(getattr(latest, "date", "—"))[:10]
    return PulseCard(
        "flow",
        "Foreign flow",
        head,
        sub,
        (
            ("Latest", latest_s),
            ("20d net", net20),
            ("Session", sess),
            ("5d days", f"{buy5 or 0}B / {sell5 or 0}S"),
        ),
        head_tone,
    )


def _pulse_structure(ps: Any) -> PulseCard:
    if ps is None:
        return PulseCard(
            "struct",
            "Structure",
            "—",
            "no price structure",
            (("52w low", "—"), ("52w high", "—"), ("Vol day", "—"), ("20d avg", "—")),
            "neutral",
        )
    vol_vs = getattr(ps, "volume_vs_20d", None)
    pos = getattr(ps, "range_52w_pct", None)
    head = "—"
    if vol_vs is not None:
        try:
            head = f"{float(vol_vs):.2f}×"
        except (TypeError, ValueError):
            head = str(vol_vs)
    sub_bits = []
    if vol_vs is not None:
        sub_bits.append("Vol vs 20d avg")
    if pos is not None:
        try:
            sub_bits.append(f"pos {float(pos):.0f}% of 52w")
        except (TypeError, ValueError):
            pass
    sub = " · ".join(sub_bits) if sub_bits else "structure"
    return PulseCard(
        "struct",
        "Structure",
        head,
        sub,
        (
            ("52w low", _fmt_price(getattr(ps, "low_52w", None))),
            ("52w high", _fmt_price(getattr(ps, "high_52w", None))),
            ("Vol day", _fmt_vol(getattr(ps, "volume", None))),
            ("20d avg", _fmt_vol(getattr(ps, "avg_volume_20d", None))),
        ),
        "neutral",
    )


def _pulse_bandar(snap: Any) -> PulseCard:
    if snap is None:
        return PulseCard(
            "bandar",
            "Bandar",
            "—",
            "no bandar snapshot",
            (("Today", "—"), ("5d", "—"), ("Top1", "—"), ("Top10", "—")),
            "neutral",
        )
    overall = str(getattr(snap, "broker_accdist", None) or "—")
    broad = getattr(snap, "broad_score", None)
    if broad is None and hasattr(snap, "accumulation_score"):
        broad = getattr(snap, "accumulation_score", None)
    try:
        broad_s = f"{int(broad):+d}" if broad is not None else "—"
    except (TypeError, ValueError):
        broad_s = str(broad)
    head = f"{overall} · {broad_s}" if broad_s != "—" else overall
    tone = "neutral"
    if str(overall).lower().startswith("acc"):
        tone = "pos"
    elif str(overall).lower() in {"dis", "dist"} or "dist" in str(overall).lower():
        tone = "neg"
    sess = str(getattr(snap, "session_date", "—"))[:10]
    top1 = str(getattr(snap, "top1_accdist", None) or "—")
    top1p = getattr(snap, "top1_percent", None)
    if top1p is not None:
        try:
            top1 = f"{top1} {float(top1p):.0f}%"
        except (TypeError, ValueError):
            pass
    return PulseCard(
        "bandar",
        "Bandar",
        head,
        f"Overall · Broad {broad_s} · session {sess}",
        (
            ("Today", str(getattr(snap, "today_accdist", None) or "—")),
            ("5d", str(getattr(snap, "five_day_accdist", None) or "—")),
            ("Top1", top1),
            ("Top10", str(getattr(snap, "top10_accdist", None) or "—")),
        ),
        tone,
    )


def _earnings_rows(records: Any) -> list[EarnRow]:
    rows: list[EarnRow] = []
    items = list(records or [])
    # newest first if sortable
    try:
        items = sorted(
            items,
            key=lambda r: (int(getattr(r, "year", 0) or 0), int(getattr(r, "quarter", 0) or 0)),
            reverse=True,
        )
    except Exception:
        pass
    eps_vals: list[float] = []
    for r in items[:4]:
        eps = getattr(r, "eps_actual", None)
        try:
            if eps is not None:
                eps_vals.append(float(eps))
        except (TypeError, ValueError):
            pass
    max_eps = max(eps_vals) if eps_vals else 0.0
    for r in items[:4]:
        y = getattr(r, "year", "?")
        q = getattr(r, "quarter", "?")
        period = f"Q{q} {y}"
        eps = getattr(r, "eps_actual", None)
        eps_s = _fmt_num(eps) if eps is not None else "—"
        yoy_s, yoy_tone = "—", "neutral"
        # YoY as % if we have prev year eps
        prev = getattr(r, "eps_prev_year", None)
        yoy_chg = getattr(r, "eps_yoy_change", None)
        if prev not in (None, 0) and eps is not None:
            try:
                pct = (float(eps) - float(prev)) / abs(float(prev)) * 100.0
                yoy_s, yoy_tone = _fmt_pct(pct)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        elif yoy_chg is not None and prev not in (None, 0):
            try:
                pct = float(yoy_chg) / abs(float(prev)) * 100.0
                yoy_s, yoy_tone = _fmt_pct(pct)
            except (TypeError, ValueError, ZeroDivisionError):
                yoy_s = str(yoy_chg)
        bar = 40
        try:
            if eps is not None and max_eps > 0:
                bar = max(8, min(100, int(float(eps) / max_eps * 100)))
        except (TypeError, ValueError):
            pass
        rows.append(EarnRow(period, eps_s, yoy_s, yoy_tone, bar))
    return rows


def _secondary_kv(dashboard: Any) -> list[tuple[str, str]]:
    """Collapsed secondary — presence only, not full CLI panels."""
    out: list[tuple[str, str]] = []
    analyst = getattr(dashboard, "analyst", None)
    out.append(("Analyst", "present" if analyst is not None else "— local"))
    own = getattr(dashboard, "ownership", None)
    out.append(("Ownership", "from cache" if own is not None else "—"))
    insider = getattr(dashboard, "insider_txns", None) or ()
    out.append(("Insider", "panel ok" if insider else "—"))
    iev = getattr(dashboard, "iev_rows", None) or ()
    out.append(("IEV / NCP", "present" if iev else "—"))
    season = getattr(dashboard, "seasonality", None)
    out.append(("Seasonality", "present" if season is not None else "—"))
    out.append(("Depth", "expand stays local panels · not Action"))
    return out


def _window_net(points: list[Any], days: int) -> tuple[str, str]:
    if not points or days <= 0:
        return "—", "neutral"
    window = points[-days:] if len(points) >= days else points
    total = 0.0
    for p in window:
        try:
            total += float(getattr(p, "net_val", 0) or 0)
        except (TypeError, ValueError):
            pass
    return _fmt_idr(total)


def _window_buy_sell(points: list[Any], days: int) -> tuple[int | None, int | None]:
    if not points:
        return None, None
    window = points[-days:] if len(points) >= days else points
    buy = sell = 0
    for p in window:
        try:
            v = float(getattr(p, "net_val", 0) or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            buy += 1
        elif v < 0:
            sell += 1
    return buy, sell


# ── format helpers ─────────────────────────────────────────


def _fmt_price(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value: Any) -> tuple[str, str]:
    if value is None:
        return "—", "neutral"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value), "neutral"
    tone = "pos" if v > 0 else ("neg" if v < 0 else "neutral")
    return f"{v:+.1f}%", tone


def _fmt_pct_value(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_num(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_int(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _fmt_mcap(value: Any) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    t = v / 1_000_000_000_000.0
    if t >= 1:
        return f"{t:.0f}T"
    b = v / 1_000_000_000.0
    if b >= 1:
        return f"{b:.0f}B"
    return f"{v:.0f}"


def _fmt_idr(value: Any) -> tuple[str, str]:
    if value is None:
        return "—", "neutral"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value), "neutral"
    tone = "pos" if v > 0 else ("neg" if v < 0 else "neutral")
    av = abs(v)
    sign = "+" if v > 0 else ("−" if v < 0 else "")
    if av >= 1_000_000_000_000:
        return f"{sign}{av / 1_000_000_000_000:.2f}T", tone
    if av >= 1_000_000_000:
        return f"{sign}{av / 1_000_000_000:.1f}B", tone
    if av >= 1_000_000:
        return f"{sign}{av / 1_000_000:.1f}M", tone
    return f"{sign}{av:.0f}", tone


def _fmt_vol(value: Any) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    return f"{v:.0f}"


def _bar_from_abs(v: float, scale: float) -> int:
    try:
        return max(8, min(100, int(abs(v) / scale * 100)))
    except Exception:
        return 20


def bar_glyphs(pct: int, *, width: int = 10) -> str:
    """Monospace bar for horizon / earnings (density only, not a chart claim)."""
    n = max(0, min(width, int(round(width * max(0, min(100, pct)) / 100.0))))
    return "█" * n + "░" * (width - n)
