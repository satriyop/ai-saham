"""Ticker desk model for Harga-mast widget (design: tui-ticker-desk.html).

Cache dashboard facts only — never Action / ENTER / WATCH / AVOID.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TickerMetric:
    label: str
    value: str


@dataclass(frozen=True)
class TickerHorizon:
    label: str
    value: str
    tone: str = "neutral"  # pos | neg | neutral


@dataclass(frozen=True)
class TickerDeskModel:
    """Everything the Harga-mast widget needs to paint (no IO)."""

    ticker: str
    name: str
    board: str
    sector: str
    price: str
    change_1d: str
    change_tone: str  # pos | neg | neutral
    as_of: str
    horizons: tuple[TickerHorizon, ...]
    metrics: tuple[TickerMetric, ...]
    freshness: tuple[str, ...]
    authority: str
    body: str
    footer: str

    def as_text(self) -> str:
        """Scraper / fallback plain-ish text (mast first, then body)."""
        lines = [
            f"View · ticker · {self.ticker}",
            "HARGA MAST",
            self.price,
        ]
        if self.change_1d:
            lines.append(self.change_1d)
        lines.append(f"as_of {self.as_of} · {self.authority}")
        lines.append("not Action authority · local cache only")
        lines.append("")
        if self.body:
            lines.append(self.body.strip())
        return "\n".join(lines)


def build_ticker_desk_model_from_dashboard(
    dashboard: Any,
    *,
    body: str = "",
) -> TickerDeskModel:
    """Build model from GetTickerDashboardUseCase result."""
    ticker = str(getattr(dashboard, "ticker", "?") or "?").upper()
    close = getattr(dashboard, "latest_close", None)
    price = _fmt_price(close)
    as_of = getattr(dashboard, "as_of", None)
    as_of_s = str(as_of)[:10] if as_of is not None else "—"

    notation = getattr(dashboard, "notation", None)
    name = "—"
    board = "—"
    sector = "—"
    if notation is not None:
        name = str(getattr(notation, "description", None) or getattr(notation, "name", None) or "—")
        # TickerNotationSnapshot shape
        board = str(getattr(notation, "listing_board", None) or board)
        sector = str(getattr(notation, "sector", None) or sector)
        if name == "—" and hasattr(notation, "notations"):
            ns = getattr(notation, "notations", None) or ()
            if ns:
                name = str(getattr(ns[0], "description", None) or "—")

    profile = getattr(dashboard, "profile", None)
    if profile is not None:
        if board == "—":
            board = str(getattr(profile, "listing_board", None) or "—")
        if name == "—":
            name = str(
                getattr(profile, "name", None) or getattr(profile, "company_name", None) or "—"
            )

    ps = getattr(dashboard, "price_structure", None)
    change_1d = "—"
    change_tone = "neutral"
    horizons: list[TickerHorizon] = []
    if ps is not None:
        c1 = getattr(ps, "change_1d_pct", None)
        change_1d, change_tone = _fmt_pct(c1)
        for lab, attr in (
            ("1d", "change_1d_pct"),
            ("5d", "change_5d_pct"),
            ("20d", "change_20d_pct"),
            ("52w", "range_52w_pct"),
        ):
            raw = getattr(ps, attr, None)
            val, tone = _fmt_pct(raw)
            if lab == "52w" and raw is not None:
                # range position is 0–100 style, not a return
                try:
                    val = f"{float(raw):.0f}%"
                    tone = "neutral"
                except (TypeError, ValueError):
                    pass
            horizons.append(TickerHorizon(lab, val, tone))
        if not horizons:
            horizons = [TickerHorizon("1d", change_1d, change_tone)]
    else:
        horizons = (
            TickerHorizon("1d", "—"),
            TickerHorizon("5d", "—"),
            TickerHorizon("20d", "—"),
            TickerHorizon("52w", "—"),
        )

    fund = getattr(dashboard, "fundamentals", None)
    metrics: list[TickerMetric] = []
    if fund is not None:
        metrics.extend(
            [
                TickerMetric("PE TTM", _fmt_num(getattr(fund, "pe_ratio_ttm", None))),
                TickerMetric("PBV", _fmt_num(getattr(fund, "pbv", None))),
                TickerMetric("MCap", _fmt_mcap(getattr(fund, "market_cap_idr", None))),
                TickerMetric("ROE", _fmt_pct_value(getattr(fund, "roe_ttm", None))),
                TickerMetric("Div yield", _fmt_pct_value(getattr(fund, "dividend_yield", None))),
                TickerMetric("F-Score", _fmt_int(getattr(fund, "piotroski_f_score", None))),
            ]
        )
    else:
        metrics = (
            TickerMetric("PE TTM", "—"),
            TickerMetric("PBV", "—"),
            TickerMetric("MCap", "—"),
            TickerMetric("ROE", "—"),
            TickerMetric("Div yield", "—"),
            TickerMetric("F-Score", "—"),
        )

    fresh_items = getattr(dashboard, "freshness", None) or ()
    freshness: list[str] = []
    for item in fresh_items[:10]:
        label = str(getattr(item, "label", None) or getattr(item, "key", "?") or "?")
        st = getattr(item, "status", None)
        st_s = str(getattr(st, "value", st) or "").lower()
        mark = "·"
        if st_s in {"ok"}:
            mark = "✓"
        elif st_s in {"missing", "empty", "error"}:
            mark = "✗"
        elif st_s in {"stale"}:
            mark = "~"
        freshness.append(f"{mark}{label}")

    return TickerDeskModel(
        ticker=ticker,
        name=name if name else "—",
        board=board if board else "—",
        sector=sector if sector else "—",
        price=price,
        change_1d=change_1d if change_1d != "—" else "",
        change_tone=change_tone,
        as_of=as_of_s,
        horizons=tuple(horizons),
        metrics=tuple(metrics),
        freshness=tuple(freshness),
        authority="cache dashboard · not Action",
        body=(body or "").strip(),
        footer="esc back · b top desks · v t re-open · local cache · no judgment",
    )


def build_ticker_desk_model_from_text(*, ticker: str, body: str) -> TickerDeskModel:
    """Fallback when only preformatted text is available (tests / stub loaders)."""
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
        price=price,
        change_1d="",
        change_tone="neutral",
        as_of="—",
        horizons=(
            TickerHorizon("1d", "—"),
            TickerHorizon("5d", "—"),
            TickerHorizon("20d", "—"),
            TickerHorizon("52w", "—"),
        ),
        metrics=(
            TickerMetric("PE TTM", "—"),
            TickerMetric("PBV", "—"),
            TickerMetric("MCap", "—"),
            TickerMetric("ROE", "—"),
            TickerMetric("Div yield", "—"),
            TickerMetric("F-Score", "—"),
        ),
        freshness=(),
        authority="cache dashboard · not Action",
        body=(body or "").strip(),
        footer="esc back · b top desks · local cache · no judgment",
    )


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
    # IDR → trillions
    t = v / 1_000_000_000_000.0
    if t >= 1:
        return f"{t:.0f}T"
    b = v / 1_000_000_000.0
    if b >= 1:
        return f"{b:.0f}B"
    return f"{v:.0f}"
