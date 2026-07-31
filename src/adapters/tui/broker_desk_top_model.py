"""Structured desk top-stocks dual-heat model (present-only).

Latest session only · net buy + net sell sides.
Builds from ViewBrokerDeskTopStocksResult — no re-ranking.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.trade_action_labels import ACTION_SCAN_TOKENS
from src.adapters.shared.view_number_format import format_value
from src.domain.entities.broker_flow import BrokerType

DISPLAY_LIMIT: int = 12
HUB_KEYS = "t buy/sell · f flow · c calendar · h history · m top 5 · v ticker · esc home"


@dataclass(frozen=True)
class BrokerTopHeatRow:
    """One heat row on buy or sell side."""

    ticker: str
    net_display: str
    lot_display: str
    bar_pct: int  # 0–100 relative within that side
    tone: str  # pos | neg


@dataclass(frozen=True)
class BrokerDeskTopModel:
    """Dual-side latest-session heat for hub ``t``."""

    broker_code: str
    broker_name: str
    type_label: str
    session_date: str
    scope_note: str
    buys: tuple[BrokerTopHeatRow, ...]
    sells: tuple[BrokerTopHeatRow, ...]
    hub_keys: str
    jump_ticker: str | None
    empty: bool = False
    empty_reason: str = ""

    def body_contains_action_authority(self) -> bool:
        blobs = [self.scope_note, self.hub_keys, self.empty_reason]
        for r in (*self.buys, *self.sells):
            blobs.append(r.ticker)
        text = " ".join(blobs).upper()
        for token in ACTION_SCAN_TOKENS[:3]:
            if token in f" {text} ":
                return True
        return False


def _type_label(broker_type: Any) -> str:
    if broker_type == BrokerType.FOREIGN:
        return "Foreign"
    if broker_type == BrokerType.LOCAL:
        return "Local"
    if isinstance(broker_type, str):
        return broker_type
    return "—"


def _signed_net(value: Decimal) -> str:
    base = format_value(value)
    if value > 0 and not base.startswith("+"):
        return f"+{base}"
    return base


def _heat_rows(rows: Any, *, limit: int, side: str) -> tuple[BrokerTopHeatRow, ...]:
    items = list(rows or ())[:limit]
    if not items:
        return ()
    abs_vals = [abs(Decimal(str(getattr(r, "net_value", 0) or 0))) for r in items]
    peak = max(abs_vals) if abs_vals else Decimal("0")
    out: list[BrokerTopHeatRow] = []
    for r, av in zip(items, abs_vals, strict=True):
        nv = Decimal(str(getattr(r, "net_value", 0) or 0))
        lot = int(getattr(r, "net_lot", 0) or 0)
        if peak > 0:
            pct = int(min(100, max(1, round(float(av / peak) * 100))))
        else:
            pct = 0
        tone = "pos" if nv > 0 else ("neg" if nv < 0 else "pos" if side == "buy" else "neg")
        out.append(
            BrokerTopHeatRow(
                ticker=str(getattr(r, "ticker", "—")).upper(),
                net_display=_signed_net(nv),
                lot_display=f"lot {lot:,}",
                bar_pct=pct,
                tone=tone,
            )
        )
    return tuple(out)


def build_broker_desk_top_model(
    result: Any | None,
    *,
    code: str = "",
    limit: int = DISPLAY_LIMIT,
    empty_reason: str = "",
) -> BrokerDeskTopModel:
    """Pure present model from top-stocks use-case result (latest session)."""
    if result is None:
        code_u = str(code or "—").upper()
        return BrokerDeskTopModel(
            broker_code=code_u,
            broker_name=code_u,
            type_label="—",
            session_date="—",
            scope_note="Tracked desk activity only · latest session",
            buys=(),
            sells=(),
            hub_keys=HUB_KEYS,
            jump_ticker=None,
            empty=True,
            empty_reason=empty_reason
            or "no broker_daily_flow for this desk · run broker fetch first",
        )

    code_u = str(getattr(result, "broker_code", code) or code or "—").upper()
    d = getattr(result, "date", None)
    date_s = d.isoformat() if hasattr(d, "isoformat") else str(d or "—")
    buys = _heat_rows(getattr(result, "top_buy_stocks", ()), limit=limit, side="buy")
    sells = _heat_rows(getattr(result, "top_sell_stocks", ()), limit=limit, side="sell")
    jump = buys[0].ticker if buys else (sells[0].ticker if sells else None)
    empty = not buys and not sells
    return BrokerDeskTopModel(
        broker_code=code_u,
        broker_name=str(getattr(result, "broker_name", code_u) or code_u),
        type_label=_type_label(getattr(result, "broker_type", None)),
        session_date=date_s,
        scope_note=str(
            getattr(result, "scope_note", None) or "Tracked desk activity only (broker_daily_flow)"
        )
        + " · latest session",
        buys=buys,
        sells=sells,
        hub_keys=HUB_KEYS,
        jump_ticker=jump,
        empty=empty,
        empty_reason="no net buy/sell names this session" if empty else "",
    )


def format_broker_desk_top_scraper_text(model: BrokerDeskTopModel) -> str:
    """Plain-text mirror for scrapers reading _detail_text."""
    lines = [
        f"Desk Top Stocks · {model.broker_code} ({model.broker_name})",
        f"type {model.type_label} · date {model.session_date}",
        model.scope_note,
        "",
        "Net buy (desk)",
    ]
    if model.buys:
        for r in model.buys:
            lines.append(f"  {r.ticker:6}  {r.net_display:>10}  {r.lot_display}")
    else:
        lines.append("  —")
    lines.append("")
    lines.append("Net sell (desk)")
    if model.sells:
        for r in model.sells:
            lines.append(f"  {r.ticker:6}  {r.net_display:>10}  {r.lot_display}")
    else:
        lines.append("  —")
    lines.append("")
    lines.append("Actions (TUI)")
    lines.append(f"  {model.hub_keys}")
    return "\n".join(lines)
