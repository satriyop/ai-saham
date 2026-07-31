"""Structured Broker desk-home model (present-only).

Builds from ViewBrokerDeskShowResult + DeskSessionPulse — no ranking,
no fetch policy. Browse-only: never carries Action / ENTER / WATCH.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.view_number_format import format_value
from src.domain.entities.broker_flow import BrokerType

# Operator hub keys (Stage 1) — deep pages stay plain text.
HUB_KEY_LEGEND = "t buy/sell · f flow · c calendar · h history · m top 5 · v ticker · esc trail"


@dataclass(frozen=True)
class BrokerDeskHomeSideStat:
    """One pulse / identity fact beside the day-net hero."""

    key: str
    value: str
    tone: str = "neutral"  # pos | neg | neutral


@dataclass(frozen=True)
class BrokerDeskHomeStockRow:
    ticker: str
    net_display: str
    tone: str  # pos | neg


@dataclass(frozen=True)
class BrokerDeskHomeModel:
    """Everything the desk-home widget needs to paint (no IO)."""

    broker_code: str
    broker_name: str
    type_label: str
    as_of: str
    day_net_sign: str
    day_net_amount: str
    day_net_tone: str  # pos | neg | flat
    day_net_sub: str
    scope_note: str
    side_stats: tuple[BrokerDeskHomeSideStat, ...]
    top_buy: tuple[BrokerDeskHomeStockRow, ...]
    top_sell: tuple[BrokerDeskHomeStockRow, ...]
    hub_keys: str
    jump_ticker: str | None
    empty: bool = False
    empty_reason: str = ""

    def body_contains_action_authority(self) -> bool:
        """True if any operator-facing string invents ENTER/WATCH/AVOID Action."""
        blobs = [
            self.scope_note,
            self.day_net_sub,
            self.hub_keys,
            self.empty_reason,
            *(s.value for s in self.side_stats),
            *(r.ticker for r in self.top_buy),
            *(r.ticker for r in self.top_sell),
        ]
        text = " ".join(blobs).upper()
        # Exact Action tokens only — avoid matching substrings in ticker codes.
        for token in (" ENTER ", " WATCH ", " AVOID ", "ENTER/", "WATCH/", "AVOID/"):
            if token in f" {text} ":
                return True
        if text.strip() in {"ENTER", "WATCH", "AVOID"}:
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


def _signed_amount(value: Decimal) -> tuple[str, str, str]:
    """Return (sign, absolute formatted amount, tone)."""
    if value > 0:
        return "+", format_value(value), "pos"
    if value < 0:
        return "−", format_value(abs(value)), "neg"
    return "", format_value(value), "flat"


def _stock_rows(rows: Any, *, limit: int = 5) -> tuple[BrokerDeskHomeStockRow, ...]:
    out: list[BrokerDeskHomeStockRow] = []
    for row in list(rows or ())[:limit]:
        net = getattr(row, "net_value", None)
        if net is None:
            continue
        sign, amt, tone = _signed_amount(Decimal(str(net)))
        display = f"{sign}{amt}" if sign else amt
        out.append(
            BrokerDeskHomeStockRow(
                ticker=str(getattr(row, "ticker", "—")).upper(),
                net_display=display,
                tone=tone,
            )
        )
    return tuple(out)


def build_broker_desk_home_model(
    result: Any | None,
    *,
    pulse: Any | None = None,
    code: str = "",
    empty_reason: str = "",
) -> BrokerDeskHomeModel:
    """Pure present model from desk show result + optional session pulse."""
    if result is None:
        code_u = str(code or "—").upper()
        return BrokerDeskHomeModel(
            broker_code=code_u,
            broker_name=code_u,
            type_label="—",
            as_of="—",
            day_net_sign="",
            day_net_amount="—",
            day_net_tone="flat",
            day_net_sub="no broker_daily_flow for this desk",
            scope_note="Tracked desk activity only",
            side_stats=(),
            top_buy=(),
            top_sell=(),
            hub_keys=HUB_KEY_LEGEND,
            jump_ticker=None,
            empty=True,
            empty_reason=empty_reason
            or "no broker_daily_flow for this desk · run broker fetch first",
        )

    code_u = str(getattr(result, "broker_code", code) or code or "—").upper()
    day_net = Decimal(str(getattr(result, "day_net_value", 0) or 0))
    sign, amount, tone = _signed_amount(day_net)
    lot = int(getattr(result, "day_net_lot", 0) or 0)
    tickers = int(getattr(result, "day_ticker_count", 0) or 0)
    as_of = getattr(result, "as_of", None)
    as_of_s = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of or "—")

    top_buy = _stock_rows(getattr(result, "top_buy_stocks", ()))
    top_sell = _stock_rows(getattr(result, "top_sell_stocks", ()))
    jump = top_buy[0].ticker if top_buy else (top_sell[0].ticker if top_sell else None)

    # Pulse side stats (desk-wide, not market foreign total)
    net5_s = "—"
    net5_tone = "neutral"
    streak_s = "—"
    delta1_s = "—"
    delta1_tone = "neutral"
    if pulse is not None:
        net5 = getattr(pulse, "net5", None)
        if net5 is not None:
            s5, a5, t5 = _signed_amount(Decimal(str(net5)))
            sess = int(getattr(pulse, "sessions_in_net5", 0) or 0)
            net5_s = f"{s5}{a5}" if s5 else a5
            if sess:
                net5_s = f"{net5_s} ({sess}s)"
            net5_tone = t5 if t5 != "flat" else "neutral"
        streak = getattr(pulse, "buy_streak", None)
        if streak is not None:
            streak_s = f"{int(streak)} sessions"
        d1 = getattr(pulse, "delta1", None)
        if d1 is not None:
            sd, ad, td = _signed_amount(Decimal(str(d1)))
            delta1_s = f"{sd}{ad}" if sd else ad
            delta1_tone = td if td != "flat" else "neutral"

    top_name = jump or "—"
    side = (
        BrokerDeskHomeSideStat("Net5", net5_s, net5_tone),
        BrokerDeskHomeSideStat("Buy streak", streak_s),
        BrokerDeskHomeSideStat("Δ1", delta1_s, delta1_tone),
        BrokerDeskHomeSideStat("Top buy", top_name),
    )

    sub = (
        f"lot {lot:,} · desk {code_u} only · {tickers} tickers · tracked activity · not full market"
    )
    scope = str(
        getattr(result, "scope_note", None) or "Tracked desk activity only (broker_daily_flow)"
    )

    return BrokerDeskHomeModel(
        broker_code=code_u,
        broker_name=str(getattr(result, "broker_name", code_u) or code_u),
        type_label=_type_label(getattr(result, "broker_type", None)),
        as_of=as_of_s,
        day_net_sign=sign,
        day_net_amount=amount,
        day_net_tone=tone,
        day_net_sub=sub,
        scope_note=scope,
        side_stats=side,
        top_buy=top_buy,
        top_sell=top_sell,
        hub_keys=HUB_KEY_LEGEND,
        jump_ticker=jump,
        empty=False,
    )


def format_broker_desk_home_scraper_text(model: BrokerDeskHomeModel) -> str:
    """Plain-text mirror for tests / scrapers that still read _detail_text."""
    if model.empty:
        return f"{model.broker_code}\n\n{model.empty_reason}\n\nActions (TUI)\n  {model.hub_keys}\n"
    lines = [
        f"Broker Desk · {model.broker_code} ({model.broker_name})",
        f"type {model.type_label} · as of {model.as_of}",
        f"Day net {model.day_net_sign}{model.day_net_amount} · {model.day_net_sub}",
        model.scope_note,
        "",
    ]
    for s in model.side_stats:
        lines.append(f"{s.key}: {s.value}")
    lines.append("")
    lines.append("Top buy stocks")
    if model.top_buy:
        for r in model.top_buy:
            lines.append(f"  {r.ticker:6}  {r.net_display}")
    else:
        lines.append("  —")
    lines.append("")
    lines.append("Top sell stocks")
    if model.top_sell:
        for r in model.top_sell:
            lines.append(f"  {r.ticker:6}  {r.net_display}")
    else:
        lines.append("  —")
    lines.append("")
    lines.append("Actions (TUI)")
    lines.append(f"  {model.hub_keys}")
    return "\n".join(lines)
