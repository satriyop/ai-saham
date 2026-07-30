"""
JSON serialization for the ticker dashboard DTO.

Aligns overview metadata with stock deep-dive envelope vocabulary so CLI and
future TUI share one status/source language.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.application.dto.ticker_dashboard import TickerDashboard
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    build_view_envelope,
)
from src.application.services.ticker_dashboard_flow import (
    FOREIGN_FLOW_WINDOWS,
    window_buy_sell_days,
    window_net,
)
from src.application.services.ticker_dashboard_price_structure import price_structure_to_dict
from src.application.services.ticker_dashboard_status import CacheStatus, FreshnessItem


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, CacheStatus):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    return str(value)


def _freshness_to_dict(
    items: list[FreshnessItem] | tuple[FreshnessItem, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "key": item.key,
            "label": item.label,
            "status": item.status.value,
            "as_of": item.as_of.isoformat() if item.as_of else None,
            "age_days": item.age_days,
            "detail": item.detail,
        }
        for item in items
    ]


def _optional_to_dict(obj: Any) -> dict[str, Any] | None:
    if obj is None:
        return None
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _json_safe(obj.to_dict())
    data: dict[str, Any] = {}
    for key, value in getattr(obj, "__dict__", {}).items():
        if key.startswith("_"):
            continue
        data[key] = _json_safe(value)
    return data or None


def _candles_to_list(candles: list | tuple, *, limit: int = 5) -> list[dict[str, Any]]:
    recent = sorted(candles, key=lambda c: c.date, reverse=True)[:limit]
    return [_json_safe(c.to_dict()) for c in recent]


def _flow_points_summary(points: list | tuple, *, source: str | None) -> dict[str, Any] | None:
    if not points:
        return None
    latest = points[-1]
    windows = {}
    for days in FOREIGN_FLOW_WINDOWS:
        net = window_net(list(points), days)
        buy_days, sell_days = window_buy_sell_days(list(points), days)
        windows[f"{days}d"] = {
            "net_val": str(net) if net is not None else None,
            "buy_days": buy_days,
            "sell_days": sell_days,
        }
    return {
        "source": source,
        "latest": {
            "date": latest.date.isoformat(),
            "net_val": str(latest.net_val),
            "net_lot": latest.net_lot,
        },
        "windows": windows,
        "point_count": len(points),
    }


def _dashboard_data(dashboard: TickerDashboard) -> dict[str, Any]:
    panels = set(dashboard.panel_keys)
    data: dict[str, Any] = {
        "mode": dashboard.mode,
        "panels": list(dashboard.panel_keys),
        "freshness": _freshness_to_dict(dashboard.freshness),
        "related_actions": [
            {"verb": a.verb, "label": a.label, "command": a.command}
            for a in dashboard.related_actions
        ],
        "panel_errors": [{"key": e.key, "message": e.message} for e in dashboard.panel_errors],
    }

    if "identity" in panels:
        data["identity"] = _optional_to_dict(dashboard.notation)
    if "valuation" in panels:
        data["valuation"] = {
            "fundamentals": _optional_to_dict(dashboard.fundamentals),
            "forward_estimates": _optional_to_dict(dashboard.forward_estimates),
            "latest_close": (
                str(dashboard.latest_close) if dashboard.latest_close is not None else None
            ),
        }
    if "price_structure" in panels:
        data["price_structure"] = price_structure_to_dict(dashboard.price_structure)
    if "analyst" in panels:
        data["analyst"] = _optional_to_dict(dashboard.analyst)
    if "earnings" in panels:
        data["earnings"] = [_json_safe(r.to_dict()) for r in dashboard.earnings]
    if "ownership" in panels:
        data["ownership"] = _optional_to_dict(dashboard.ownership)
    if "bandar" in panels:
        data["bandar"] = _optional_to_dict(dashboard.bandar)
    if "foreign_flow" in panels:
        data["foreign_flow"] = _flow_points_summary(
            dashboard.foreign_flow_points,
            source=dashboard.foreign_flow_source,
        )
    if "sector_macro" in panels:
        smc = dashboard.sector_macro_context_evidence
        data["sector_macro_context_evidence"] = (
            {
                **smc.to_dict(),
                "diagnostic": True,
                "authority": "DIAGNOSTIC",
                "judgment_command": f"saham screen accum {dashboard.ticker}",
            }
            if smc is not None
            else None
        )
    if "corp_actions" in panels:
        data["corp_actions"] = [_optional_to_dict(e) for e in dashboard.corp_actions]
    if "insider" in panels:
        data["insider"] = {
            "transactions": [_optional_to_dict(t) for t in dashboard.insider_txns[:20]],
            "last_known_outside_window": (
                dashboard.insider_last_known.isoformat() if dashboard.insider_last_known else None
            ),
            "status": dashboard.insider_status.value,
        }
    if "seasonality" in panels:
        data["seasonality"] = _optional_to_dict(dashboard.seasonality)
    if "iev" in panels:
        data["iev"] = [_optional_to_dict(r) for r in dashboard.iev_rows[:10]]
    if "sentiment" in panels:
        data["sentiment"] = [_optional_to_dict(s) for s in dashboard.sentiment_logs[:20]]
    if "profile" in panels:
        data["profile"] = _optional_to_dict(dashboard.profile)
    if "candles" in panels:
        data["candles"] = _candles_to_list(dashboard.candles, limit=5)

    return data


def ticker_dashboard_to_json_dict(dashboard: TickerDashboard) -> dict[str, Any]:
    """Serialize dashboard using the shared view envelope vocabulary."""
    status = (
        ViewResultStatus.OK
        if not dashboard.panel_errors
        else ViewResultStatus.OK  # partial success still ok; errors live in data
    )
    # If everything critical is missing, still return ok with empty panels — CLI
    # show is multi-panel and rarely fully missing.
    envelope = build_view_envelope(
        subject_id=dashboard.ticker,
        verb="show",
        status=status,
        as_of=dashboard.as_of,
        source="ticker_dashboard",
        scope="brief" if dashboard.mode == "brief" else "full",
        fetch_hint=dashboard.fetch_hint,
        data=_dashboard_data(dashboard),
    )
    return envelope
