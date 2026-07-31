"""Structured desk flow-by-day model (present-only).

Builds from ViewBrokerDeskFlowResult — desk day nets, not market foreign total.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.view_number_format import format_value
from src.domain.entities.broker_flow import BrokerType

DISPLAY_LIMIT: int = 20
HUB_KEYS = "t buy/sell · f flow · c calendar · h history · m top 5 · v ticker · esc home"


@dataclass(frozen=True)
class BrokerFlowDayRow:
    date_label: str
    net_display: str
    lot_display: str
    ticker_count: str
    bar_pct: int
    tone: str  # pos | neg | flat


@dataclass(frozen=True)
class BrokerDeskFlowModel:
    broker_code: str
    broker_name: str
    type_label: str
    scope_note: str
    days: tuple[BrokerFlowDayRow, ...]
    hub_keys: str
    empty: bool = False
    empty_reason: str = ""

    def body_contains_action_authority(self) -> bool:
        text = f"{self.scope_note} {self.hub_keys} {self.empty_reason}".upper()
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
        return base if base.startswith("-") or base.startswith(
            "−"
        ) else f"-{base.lstrip('-')}", "neg"
    return base, "flat"


def build_broker_desk_flow_model(
    result: Any | None,
    *,
    code: str = "",
    limit: int = DISPLAY_LIMIT,
    empty_reason: str = "",
) -> BrokerDeskFlowModel:
    if result is None:
        code_u = str(code or "—").upper()
        return BrokerDeskFlowModel(
            broker_code=code_u,
            broker_name=code_u,
            type_label="—",
            scope_note="Tracked desk activity only · day nets",
            days=(),
            hub_keys=HUB_KEYS,
            empty=True,
            empty_reason=empty_reason
            or "no broker_daily_flow for this desk · run broker fetch first",
        )

    code_u = str(getattr(result, "broker_code", code) or code or "—").upper()
    raw_days = list(getattr(result, "days", ()) or ())
    # show newest first for operator scan
    raw_days = list(reversed(raw_days[-limit:]))
    abs_vals = [abs(Decimal(str(getattr(d, "net_value", 0) or 0))) for d in raw_days]
    peak = max(abs_vals) if abs_vals else Decimal("0")
    rows: list[BrokerFlowDayRow] = []
    for d, av in zip(raw_days, abs_vals, strict=True):
        nv = Decimal(str(getattr(d, "net_value", 0) or 0))
        net_s, tone = _signed(nv)
        lot = int(getattr(d, "net_lot", 0) or 0)
        tc = int(getattr(d, "ticker_count", 0) or 0)
        dt = getattr(d, "date", None)
        date_s = dt.isoformat() if hasattr(dt, "isoformat") else str(dt or "—")
        pct = int(min(100, max(1, round(float(av / peak) * 100)))) if peak > 0 else 0
        rows.append(
            BrokerFlowDayRow(
                date_label=date_s,
                net_display=net_s,
                lot_display=f"{lot:,}",
                ticker_count=str(tc),
                bar_pct=pct,
                tone=tone,
            )
        )
    empty = not rows
    return BrokerDeskFlowModel(
        broker_code=code_u,
        broker_name=str(getattr(result, "broker_name", code_u) or code_u),
        type_label=_type_label(getattr(result, "broker_type", None)),
        scope_note=str(
            getattr(result, "scope_note", None) or "Tracked desk activity only (broker_daily_flow)"
        )
        + " · day nets · not market foreign total",
        days=tuple(rows),
        hub_keys=HUB_KEYS,
        empty=empty,
        empty_reason="no day nets in window" if empty else "",
    )


def format_broker_desk_flow_scraper_text(model: BrokerDeskFlowModel) -> str:
    lines = [
        f"Desk Flow by Day · {model.broker_code} ({model.broker_name})",
        f"type {model.type_label}",
        model.scope_note,
        "",
        f"{'Date':12}  {'Net':>10}  {'Lot':>10}  Tickers",
        "-" * 44,
    ]
    if model.days:
        for d in model.days:
            lines.append(
                f"{d.date_label:12}  {d.net_display:>10}  {d.lot_display:>10}  {d.ticker_count}"
            )
    else:
        lines.append("  —")
    lines.append("")
    lines.append("Actions (TUI)")
    lines.append(f"  {model.hub_keys}")
    return "\n".join(lines)
