"""Structured desk history model (present-only).

Builds from ViewBrokerDeskHistoryResult — per-ticker daily rows for desk.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.view_number_format import format_value
from src.domain.entities.broker_flow import BrokerType

DISPLAY_LIMIT: int = 40
HUB_KEYS = "t buy/sell · f flow · c calendar · h history · m top 5 · v ticker · esc home"


@dataclass(frozen=True)
class BrokerHistoryRow:
    date_label: str
    ticker: str
    net_display: str
    lot_display: str
    tone: str  # pos | neg | flat


@dataclass(frozen=True)
class BrokerDeskHistoryModel:
    broker_code: str
    broker_name: str
    type_label: str
    scope_note: str
    pinned_ticker: str | None
    rows: tuple[BrokerHistoryRow, ...]
    truncated: int
    hub_keys: str
    jump_ticker: str | None
    empty: bool = False
    empty_reason: str = ""

    def body_contains_action_authority(self) -> bool:
        blobs = [self.scope_note, self.hub_keys, self.empty_reason]
        for r in self.rows:
            blobs.append(r.ticker)
        text = " ".join(blobs).upper()
        for token in (" ENTER ", " WATCH ", " AVOID "):
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


def _signed(value: Decimal) -> tuple[str, str]:
    base = format_value(value)
    if value > 0 and not base.startswith("+"):
        return f"+{base}", "pos"
    if value < 0:
        return base, "neg"
    return base, "flat"


def build_broker_desk_history_model(
    result: Any | None,
    *,
    code: str = "",
    limit: int = DISPLAY_LIMIT,
    empty_reason: str = "",
) -> BrokerDeskHistoryModel:
    if result is None:
        code_u = str(code or "—").upper()
        return BrokerDeskHistoryModel(
            broker_code=code_u,
            broker_name=code_u,
            type_label="—",
            scope_note="Tracked desk activity only · per-ticker daily",
            pinned_ticker=None,
            rows=(),
            truncated=0,
            hub_keys=HUB_KEYS,
            jump_ticker=None,
            empty=True,
            empty_reason=empty_reason
            or "no broker_daily_flow for this desk · run broker fetch first",
        )

    code_u = str(getattr(result, "broker_code", code) or code or "—").upper()
    flows = list(getattr(result, "flows", ()) or ())
    # newest first
    flows_sorted = sorted(
        flows,
        key=lambda f: (getattr(f, "date", None), str(getattr(f, "ticker", ""))),
        reverse=True,
    )
    shown = flows_sorted[:limit]
    truncated = max(0, len(flows_sorted) - len(shown))
    rows: list[BrokerHistoryRow] = []
    for f in shown:
        nv = Decimal(str(getattr(f, "net_value", 0) or 0))
        net_s, tone = _signed(nv)
        lot = int(getattr(f, "net_lot", 0) or 0)
        dt = getattr(f, "date", None)
        date_s = dt.isoformat() if hasattr(dt, "isoformat") else str(dt or "—")
        rows.append(
            BrokerHistoryRow(
                date_label=date_s,
                ticker=str(getattr(f, "ticker", "—")).upper(),
                net_display=net_s,
                lot_display=f"{lot:,}",
                tone=tone,
            )
        )
    pin = getattr(result, "pinned_ticker", None)
    pin_s = str(pin).upper() if pin else None
    jump = pin_s or (rows[0].ticker if rows else None)
    empty = not rows
    return BrokerDeskHistoryModel(
        broker_code=code_u,
        broker_name=str(getattr(result, "broker_name", code_u) or code_u),
        type_label=_type_label(getattr(result, "broker_type", None)),
        scope_note=str(
            getattr(result, "scope_note", None) or "Tracked desk activity only (broker_daily_flow)"
        )
        + " · per-ticker daily",
        pinned_ticker=pin_s,
        rows=tuple(rows),
        truncated=truncated,
        hub_keys=HUB_KEYS,
        jump_ticker=jump,
        empty=empty,
        empty_reason="no history rows in window" if empty else "",
    )


def format_broker_desk_history_scraper_text(model: BrokerDeskHistoryModel) -> str:
    pin = f" · ticker {model.pinned_ticker}" if model.pinned_ticker else ""
    lines = [
        f"Desk History · {model.broker_code} ({model.broker_name}){pin}",
        f"type {model.type_label}",
        model.scope_note,
        "",
        f"{'Date':12}  {'Ticker':6}  {'Net':>10}  {'Lot':>8}",
        "-" * 44,
    ]
    if model.rows:
        for r in model.rows:
            lines.append(
                f"{r.date_label:12}  {r.ticker:6}  {r.net_display:>10}  {r.lot_display:>8}"
            )
    else:
        lines.append("  —")
    if model.truncated:
        lines.append(f"  … truncated {model.truncated} more rows")
    lines.append("")
    lines.append("Actions (TUI)")
    lines.append(f"  {model.hub_keys}")
    return "\n".join(lines)
