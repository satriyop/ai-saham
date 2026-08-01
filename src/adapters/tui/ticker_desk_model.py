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
class TickerFreshPill:
    """One mock ``fresh-grid`` pill (Price / Flow / …)."""

    key: str
    label: str
    status: str  # ok | miss | stale | unknown
    value: str  # ok | — | stale | short status

    @property
    def css_kind(self) -> str:
        if self.status == "ok":
            return "ok"
        if self.status == "stale":
            return "stale"
        if self.status in {"miss", "missing", "empty", "error"}:
            return "miss"
        return "unknown"


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
    yoy_tone: str = "neutral"  # pos | neg | neutral | warn (extreme / non-comparable base)
    bar_pct: int = 50
    yoy_extreme: bool = False  # |YoY| ≥ 200% — often split / restatement base


@dataclass(frozen=True)
class TickerDetailPanel:
    """One expandable full-inventory panel summary (browse · not Action)."""

    key: str
    title: str
    status: str  # present | missing | stale
    lines: tuple[str, ...] = ()


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
    freshness: tuple[TickerFreshPill, ...]
    pulses: tuple[PulseCard, ...]
    earnings: tuple[EarnRow, ...]
    secondary: tuple[tuple[str, str], ...]
    detail_panels: tuple[TickerDetailPanel, ...]
    authority: str
    footer: str
    # Optional raw body for scrapers only — not painted as primary stage.
    body: str = ""

    def as_text(self) -> str:
        lines = [
            f"View · ticker desk · {self.ticker}",
            f"{self.name} · {self.board} · {self.sector}",
            "LAST · LOCAL CLOSE",
            f"Rp {self.price}  {self.change_1d}".strip(),
            f"as_of {self.as_of} · {self.authority}",
        ]
        if self.freshness:
            lines.append(
                "Freshness  " + "  ".join(f"{p.label}:{p.value}" for p in self.freshness[:10])
            )
        for p in self.pulses:
            lines.append(f"{p.title}: {p.headline} · {p.sub}")
        for e in self.earnings[:4]:
            lines.append(f"{e.period}  eps {e.eps}  yoy {e.yoy}")
        if self.detail_panels:
            lines.append("DETAIL PANELS")
            for d in self.detail_panels:
                lines.append(f"  {d.title}: {d.status}")
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
    detail_panels = _detail_panels(dashboard)

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
        detail_panels=tuple(detail_panels),
        authority="local cache · browse",
        footer="d detail · b desks · p plan · esc",
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
        detail_panels=(
            TickerDetailPanel(
                "stub",
                "Full inventory",
                "missing",
                ("text-only stub · press d after live dashboard load",),
            ),
        ),
        authority="local cache · browse",
        footer="d detail · b desks · p plan · esc · no order · no re-score",
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


# Fresh-grid order (bible: no Sent — cryptic Sentiment forbidden)
FRESH_GRID_LABELS: tuple[str, ...] = (
    "Price",
    "Flow",
    "Bandar",
    "Earn",
    "Fund",
    "Analyst",
    "Own",
    "IEV",
    "Insider",
)
# Widget precomposes this many slots; paint hides unused (real pills only).
FRESH_GRID_SLOTS: int = 12


def _normalize_fresh_status(raw: Any) -> tuple[str, str]:
    """Return (status, value) for a pill."""
    st_s = str(getattr(raw, "value", raw) if raw is not None else "").lower().strip()
    if st_s in {"ok", "ready", "fresh", "present"}:
        return "ok", "ok"
    if st_s in {"stale", "lag", "lagging"}:
        return "stale", "stale"
    if st_s in {"missing", "empty", "error", "miss", "absent", "—", "-", "none"}:
        return "miss", "—"
    if not st_s:
        return "miss", "—"
    return "unknown", st_s[:8] or "—"


def _short_fresh_label(label: str) -> str | None:
    """Map dashboard label → grid short name, or None to drop (e.g. Sent)."""
    low = label.lower().strip()
    if not low:
        return None
    # Never paint Sent / cryptic sentiment as a freshness cell
    if low in {"sent", "sentiment", "news", "news_sentiment"} or "sentiment" in low:
        return None
    if low in {"price", "close", "candle"}:
        return "Price"
    if low in {"flow", "foreign", "foreign_flow"}:
        return "Flow"
    if low in {"bandar", "broker"}:
        return "Bandar"
    if low in {"earn", "earnings"}:
        return "Earn"
    if low in {"fund", "fundamentals", "fundamental"}:
        return "Fund"
    if low in {"analyst", "analysts"}:
        return "Analyst"
    if low in {"own", "ownership"}:
        return "Own"
    if low in {"iev", "preopen"}:
        return "IEV"
    if low in {"insider", "insiders"}:
        return "Insider"
    for known in FRESH_GRID_LABELS:
        if known.lower() in low or low in known.lower():
            return known
    # Unknown real series: keep truncated label (still real, not Sent)
    return label[:12] if label else None


def _freshness_pills(items: Any) -> list[TickerFreshPill]:
    """Build freshness pills from **real** dashboard rows only.

    - No ``Sent`` slot.
    - Do not invent miss tiles for every known label when data is absent.
    - Order: known FRESH_GRID_LABELS first (when present), then other real keys.
    """
    by_label: dict[str, TickerFreshPill] = {}
    for item in list(items or ()):
        label = str(getattr(item, "label", None) or getattr(item, "key", None) or "").strip()
        if not label:
            continue
        short = _short_fresh_label(label)
        if short is None:
            continue
        status, value = _normalize_fresh_status(getattr(item, "status", None))
        key = short.lower().replace(" ", "_")
        by_label[short] = TickerFreshPill(key=key, label=short, status=status, value=value)

    if not by_label:
        return []

    out: list[TickerFreshPill] = []
    for lab in FRESH_GRID_LABELS:
        if lab in by_label:
            out.append(by_label[lab])
    known = set(FRESH_GRID_LABELS)
    for lab, pill in by_label.items():
        if lab not in known:
            out.append(pill)
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


# |YoY| at/above this is still real math but often non-comparable (split / restatement).
_EARNINGS_YOY_EXTREME_PCT = 200.0


def _earnings_yoy_pct(record: Any) -> float | None:
    """Prefer domain ``yoy_growth_pct``; else same-quarter prior year math.

    ``eps_yoy_change`` is signed IDR delta vs prior year — never display as %.
    """
    try:
        from src.domain.value_objects.earnings_record import EarningsRecord

        if isinstance(record, EarningsRecord):
            return record.yoy_growth_pct
    except Exception:
        pass
    # Duck-typed property / attribute
    if hasattr(record, "yoy_growth_pct"):
        try:
            v = record.yoy_growth_pct
            if v is not None and not callable(v):
                return float(v)
        except (TypeError, ValueError):
            pass
    eps = getattr(record, "eps_actual", None)
    prev = getattr(record, "eps_prev_year", None)
    if eps is None or prev in (None, 0):
        return None
    try:
        return (float(eps) - float(prev)) / abs(float(prev)) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _fmt_earnings_yoy(yoy_pct: float | None) -> tuple[str, str, bool]:
    """Format YoY growth % for desk paint.

    Returns ``(label, tone, extreme)``. Extreme = |pct| ≥ 200 — keep the real
    number, mark ``*``, tone warn (not green/red cheer for non-comparable bases).
    """
    if yoy_pct is None:
        return "—", "neutral", False
    try:
        v = float(yoy_pct)
    except (TypeError, ValueError):
        return "—", "neutral", False
    extreme = abs(v) >= _EARNINGS_YOY_EXTREME_PCT
    if extreme:
        # Integer for huge moves; * = prior-year base may be non-comparable
        return f"{v:+.0f}%*", "warn", True
    yoy_s, tone = _fmt_pct(v)
    return yoy_s, tone, False


def _earnings_rows(records: Any) -> list[EarnRow]:
    """Last 4 quarters: period · EPS · YoY% · bar = relative |EPS| (not fake)."""
    rows: list[EarnRow] = []
    items = list(records or [])
    # Dedupe (year, quarter) — cache may store multiple fetch snapshots
    try:
        items = sorted(
            items,
            key=lambda r: (int(getattr(r, "year", 0) or 0), int(getattr(r, "quarter", 0) or 0)),
            reverse=True,
        )
    except Exception:
        pass
    seen_period: set[tuple[int, int]] = set()
    deduped: list[Any] = []
    for r in items:
        key = (int(getattr(r, "year", 0) or 0), int(getattr(r, "quarter", 0) or 0))
        if key in seen_period and key != (0, 0):
            continue
        seen_period.add(key)
        deduped.append(r)
    window = deduped[:4]
    eps_vals: list[float] = []
    for r in window:
        eps = getattr(r, "eps_actual", None)
        try:
            if eps is not None:
                eps_vals.append(abs(float(eps)))
        except (TypeError, ValueError):
            pass
    max_eps = max(eps_vals) if eps_vals else 0.0
    for r in window:
        # Prefer domain period_label when present
        period = str(getattr(r, "period_label", None) or "").strip()
        if not period:
            y = getattr(r, "year", "?")
            q = getattr(r, "quarter", "?")
            period = f"Q{q} {y}"
        eps = getattr(r, "eps_actual", None)
        eps_s = _fmt_num(eps) if eps is not None else "—"
        yoy_pct = _earnings_yoy_pct(r)
        yoy_s, yoy_tone, yoy_extreme = _fmt_earnings_yoy(yoy_pct)
        bar = 0
        try:
            if eps is not None and max_eps > 0:
                # Relative to largest |EPS| in the window — real magnitude sugar
                bar = max(1, min(100, int(round(abs(float(eps)) / max_eps * 100))))
        except (TypeError, ValueError):
            bar = 0
        rows.append(EarnRow(period, eps_s, yoy_s, yoy_tone, bar, yoy_extreme))
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
    out.append(("Depth", "d expand · local panels"))
    return out


def _detail_panels(dashboard: Any) -> list[TickerDetailPanel]:
    """Full inventory for ``d`` expand — real fact lines (CLI panel fields).

    Present-only browse; never invent Action or re-score.
    """
    panels: list[TickerDetailPanel] = []

    def add(
        key: str,
        title: str,
        present: bool,
        lines: tuple[str, ...] = (),
        *,
        missing_hint: str = "not in local cache",
    ) -> None:
        if present and lines:
            panels.append(TickerDetailPanel(key, title, "present", lines))
        elif present:
            panels.append(TickerDetailPanel(key, title, "present", ("cached · no scalar fields",)))
        else:
            panels.append(TickerDetailPanel(key, title, "missing", (missing_hint,)))

    analyst = getattr(dashboard, "analyst", None)
    add("analyst", "Analyst Consensus", analyst is not None, _lines_analyst(analyst))

    own = getattr(dashboard, "ownership", None)
    add("ownership", "Ownership", own is not None, _lines_ownership(own))

    sector = getattr(dashboard, "sector_macro", None) or getattr(dashboard, "sector_context", None)
    add(
        "sector_macro",
        "Sector / macro",
        sector is not None,
        _lines_sector(sector),
        missing_hint="diagnostic omitted or missing",
    )

    corp = getattr(dashboard, "corp_actions", None) or getattr(dashboard, "corporate_actions", None)
    corp_list = list(corp) if isinstance(corp, (list, tuple)) else ([corp] if corp else [])
    corp_list = [e for e in corp_list if getattr(e, "event_type", None) != "__NONE__"]
    add("corp_actions", "Corporate Actions", bool(corp_list), _lines_corp(corp_list))

    insider = list(getattr(dashboard, "insider_txns", None) or ())
    add("insider", "Insider Transactions", bool(insider), _lines_insider(insider))

    season = getattr(dashboard, "seasonality", None)
    add("seasonality", "Seasonality", season is not None, _lines_seasonality(season))

    iev = list(getattr(dashboard, "iev_rows", None) or ())
    add("iev", "IEV / NCP", bool(iev), _lines_iev(iev))

    sent = getattr(dashboard, "sentiment", None)
    sent_list = list(sent) if isinstance(sent, (list, tuple)) else ([sent] if sent else [])
    add("sentiment", "News Sentiment", bool(sent_list), _lines_sentiment(sent_list))

    profile = getattr(dashboard, "profile", None)
    notation = getattr(dashboard, "notation", None)
    add(
        "profile",
        "Profile",
        profile is not None or notation is not None,
        _lines_profile(profile, notation),
    )

    candles = getattr(dashboard, "candles", None) or getattr(dashboard, "ohlcv", None)
    c_n = len(candles) if isinstance(candles, (list, tuple)) else (1 if candles else 0)
    add(
        "candles",
        "Candles",
        c_n > 0,
        (f"{c_n} bars in local cache",) if c_n else (),
    )

    return panels


def _lines_analyst(ac: Any) -> tuple[str, ...]:
    if ac is None:
        return ()
    lines: list[str] = []
    buy = getattr(ac, "buy_count", None)
    hold = getattr(ac, "hold_count", None)
    sell = getattr(ac, "sell_count", None)
    label = getattr(ac, "consensus_label", None)
    if callable(label):
        try:
            label = label()
        except Exception:
            label = None
    if buy is not None or hold is not None or sell is not None:
        counts = f"{buy or 0}B · {hold or 0}H · {sell or 0}S"
        if label:
            lines.append(f"{counts} → {label}")
        else:
            lines.append(counts)
    elif label:
        lines.append(str(label))
    avg = getattr(ac, "avg_price_target", None)
    upside = getattr(ac, "upside_pct", None)
    if callable(upside):
        try:
            upside = upside()
        except Exception:
            upside = None
    if avg is not None:
        try:
            t = f"Target Rp{float(avg):,.0f} avg"
            if upside is not None:
                t += f" ({float(upside):+.1f}%)"
            lines.append(t)
        except (TypeError, ValueError):
            lines.append(f"Target {avg}")
    lo = getattr(ac, "price_target_low", None)
    hi = getattr(ac, "price_target_high", None)
    if lo is not None and hi is not None:
        try:
            lines.append(f"Range Rp{float(lo):,.0f} – Rp{float(hi):,.0f}")
        except (TypeError, ValueError):
            pass
    updated = getattr(ac, "last_updated", None)
    fetched = getattr(ac, "fetched_at", None)
    meta = []
    if updated:
        meta.append(f"Updated {updated}")
    if fetched is not None:
        d = getattr(fetched, "date", None)
        meta.append(f"Fetched {d() if callable(d) else (d or fetched)}")
    if meta:
        lines.append(" · ".join(str(m) for m in meta))
    # Fallback: object present but no known fields
    return tuple(lines[:6])


def _lines_ownership(sh: Any) -> tuple[str, ...]:
    if sh is None:
        return ()
    lines: list[str] = []
    name = getattr(sh, "top_holder_name", None)
    pct = getattr(sh, "top_holder_pct", None)
    if name:
        try:
            if pct is not None:
                lines.append(f"Top Holder  {name}  {float(pct):.1f}%")
            else:
                lines.append(f"Top Holder  {name}")
        except (TypeError, ValueError):
            lines.append(f"Top Holder  {name}")
    inst = getattr(sh, "institution_pct", None)
    if inst is not None:
        try:
            lines.append(f"Institutional  {float(inst):.1f}%")
        except (TypeError, ValueError):
            lines.append(f"Institutional  {inst}")
    indiv = getattr(sh, "individual_pct", None)
    if indiv is not None:
        try:
            lines.append(f"Individual  {float(indiv):.1f}%")
        except (TypeError, ValueError):
            lines.append(f"Individual  {indiv}")
    total = getattr(sh, "total_shares_formatted", None) or getattr(sh, "total_shares", None)
    if total is not None:
        lines.append(f"Total Shares  {total}")
    rd = getattr(sh, "report_date", None)
    if rd:
        lines.append(f"Report Date  {rd}")
    return tuple(lines[:6])


def _lines_sector(sec: Any) -> tuple[str, ...]:
    if sec is None:
        return ()
    lines: list[str] = []
    for attr, lab in (
        ("sector", "Sector"),
        ("sector_name", "Sector"),
        ("regime", "Regime"),
        ("label", "Label"),
        ("peers_up_5d", "Peers up 5d"),
        ("rel_strength", "Rel strength"),
    ):
        v = getattr(sec, attr, None)
        if v is not None and str(v).strip():
            lines.append(f"{lab}  {v}")
    if not lines:
        lines.append("diagnostic · local only")
    return tuple(lines[:5])


def _lines_corp(events: list[Any]) -> tuple[str, ...]:
    lines: list[str] = []
    for e in events[:4]:
        et = str(getattr(e, "event_type", "") or "event").replace("_", " ")
        ex = getattr(e, "ex_date", None) or "—"
        detail = str(getattr(e, "detail", "") or "").strip() or "—"
        lines.append(f"{ex}  {et}  {detail}"[:72])
    if not lines and events:
        lines.append(f"{len(events)} events")
    return tuple(lines)


def _lines_insider(txns: list[Any]) -> tuple[str, ...]:
    lines: list[str] = []
    for t in txns[:4]:
        d = getattr(t, "transaction_date", None) or "—"
        name = str(getattr(t, "name", "") or "—")[:16]
        role = str(getattr(t, "role", "") or "")[:8]
        action = str(getattr(t, "action_type", "") or "—")
        shares = getattr(t, "shares", None)
        price = getattr(t, "price", None)
        sh = f"{int(shares):,}" if isinstance(shares, (int, float)) else "—"
        try:
            pr = f"Rp{float(price):,.0f}" if price else ""
        except (TypeError, ValueError):
            pr = ""
        lines.append(f"{d}  {name}  {role}  {action}  {sh}  {pr}".strip()[:72])
    if not lines and txns:
        lines.append(f"{len(txns)} transactions")
    return tuple(lines)


def _lines_seasonality(s: Any) -> tuple[str, ...]:
    if s is None:
        return ()
    lines: list[str] = []
    for attr, lab in (
        ("label", "Pattern"),
        ("edge_label", "Edge"),
        ("window", "Window"),
        ("note", "Note"),
        ("summary", "Summary"),
    ):
        v = getattr(s, attr, None)
        if v is not None and str(v).strip():
            lines.append(f"{lab}  {v}")
    if not lines:
        # object present — show compact repr of public attrs
        for attr in ("best_month", "worst_month", "avg_return"):
            v = getattr(s, attr, None)
            if v is not None:
                lines.append(f"{attr}  {v}")
    if not lines:
        lines.append("seasonality cached")
    return tuple(lines[:5])


def _lines_iev(rows: list[Any]) -> tuple[str, ...]:
    lines: list[str] = []
    for r in rows[:4]:
        d = getattr(r, "date", None) or getattr(r, "session_date", None) or "—"
        iep = getattr(r, "iep", None) or getattr(r, "price", None)
        iev = getattr(r, "iev", None)
        ncp = getattr(r, "ncp", None) or getattr(r, "iev_intensity", None)
        parts = [str(d)]
        if iep is not None:
            parts.append(f"IEP {iep}")
        if iev is not None:
            parts.append(f"IEV {iev}")
        if ncp is not None:
            parts.append(f"NCP {ncp}")
        lines.append("  ".join(parts)[:72])
    if not lines and rows:
        lines.append(f"{len(rows)} IEV rows")
    return tuple(lines)


def _lines_sentiment(logs: list[Any]) -> tuple[str, ...]:
    lines: list[str] = []
    for log in logs[:4]:
        d = getattr(log, "date", None) or "—"
        sent = getattr(log, "sentiment", None)
        if hasattr(sent, "value"):
            sent = sent.value
        cat = getattr(log, "catalyst", None)
        if hasattr(cat, "value"):
            cat = cat.value
        score = getattr(log, "score", None)
        parts = [str(d), str(sent or "—")]
        if cat:
            parts.append(str(cat).replace("_", " "))
        if score is not None:
            try:
                parts.append(f"{float(score):.2f}")
            except (TypeError, ValueError):
                parts.append(str(score))
        lines.append("  ".join(parts)[:72])
    if not lines and logs:
        lines.append(f"{len(logs)} sentiment rows")
    return tuple(lines)


def _lines_profile(profile: Any, notation: Any) -> tuple[str, ...]:
    lines: list[str] = []
    src = profile or notation
    if src is None:
        return ()
    for attr, lab in (
        ("name", "Name"),
        ("board", "Board"),
        ("sector", "Sector"),
        ("sub_sector", "Sub-sector"),
        ("listing_date", "Listed"),
        ("primary_profile", "Profile"),
        ("tradeable", "Tradeable"),
    ):
        v = getattr(src, attr, None)
        if v is not None and str(v).strip() and str(v) != "—":
            lines.append(f"{lab}  {v}")
    if not lines:
        lines.append("notation / profile cached")
    return tuple(lines[:6])


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


def bar_glyphs(pct: int, *, width: int = 10, hollow: bool = True) -> str:
    """Monospace density bar (scalar sugar only — not a chart claim).

    ``hollow=False``: filled blocks only (horizons · earnings) — no grey ░ wallpaper.
    ``hollow=True``: filled + light residual (legacy / optional).
    """
    if pct is None or int(pct) <= 0:
        return ""
    n = max(1, min(width, int(round(width * max(0, min(100, int(pct))) / 100.0))))
    if hollow:
        return "█" * n + "░" * (width - n)
    return "█" * n
