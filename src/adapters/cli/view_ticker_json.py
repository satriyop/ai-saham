"""
JSON serialization helpers for the ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.adapters.cli.view_ticker_layout import panel_keys_for_mode
from src.adapters.cli.view_ticker_price_structure import (
    PriceStructure,
    price_structure_to_dict,
)
from src.adapters.cli.view_ticker_status import CacheStatus, FreshnessItem


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


def _freshness_to_dict(items: list[FreshnessItem]) -> list[dict[str, Any]]:
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
    # Best-effort public attribute dump for frozen dataclasses without to_dict.
    data: dict[str, Any] = {}
    for key, value in getattr(obj, "__dict__", {}).items():
        if key.startswith("_"):
            continue
        data[key] = _json_safe(value)
    return data or None


def _candles_to_list(candles: list, *, limit: int = 5) -> list[dict[str, Any]]:
    recent = sorted(candles, key=lambda c: c.date, reverse=True)[:limit]
    return [_json_safe(c.to_dict()) for c in recent]


def _earnings_to_list(records: list) -> list[dict[str, Any]]:
    return [_json_safe(r.to_dict()) for r in records]


def _flow_points_summary(points: list, *, source: str | None) -> dict[str, Any] | None:
    if not points:
        return None
    latest = points[-1]
    from src.adapters.cli.view_ticker_flow_display import (
        FOREIGN_FLOW_WINDOWS,
        _window_buy_sell_days,
        _window_net,
    )

    windows = {}
    for days in FOREIGN_FLOW_WINDOWS:
        net = _window_net(points, days)
        buy_days, sell_days = _window_buy_sell_days(points, days)
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


def build_ticker_dashboard_json(
    *,
    ticker: str,
    brief: bool,
    as_of: date | None,
    freshness_items: list[FreshnessItem],
    notation: Any,
    fund: Any,
    fwd: Any,
    price_structure: PriceStructure | None,
    analyst: Any,
    earnings: list,
    ownership: Any,
    bandar: Any,
    foreign_flow_points: list,
    foreign_flow_source: str | None,
    corp_actions: list,
    insider_txns: list,
    insider_last_known: date | None,
    seasonality: Any,
    iev_rows: list,
    sentiment_logs: list,
    profile: Any,
    candles: list,
) -> dict[str, Any]:
    """Assemble a JSON-serializable ticker dashboard payload."""
    panels = panel_keys_for_mode(brief=brief)
    payload: dict[str, Any] = {
        "ticker": ticker.upper(),
        "mode": "brief" if brief else "full",
        "as_of": as_of.isoformat() if as_of else None,
        "panels": list(panels),
        "data": {},
    }
    data = payload["data"]

    if "identity" in panels:
        data["identity"] = _optional_to_dict(notation)
    if "freshness" in panels:
        data["freshness"] = _freshness_to_dict(freshness_items)
    if "valuation" in panels:
        data["valuation"] = {
            "fundamentals": _optional_to_dict(fund),
            "forward_estimates": _optional_to_dict(fwd),
            "latest_close": str(candles[-1].close) if candles else None,
        }
    if "price_structure" in panels:
        data["price_structure"] = price_structure_to_dict(price_structure)
    if "analyst" in panels:
        data["analyst"] = _optional_to_dict(analyst)
    if "earnings" in panels:
        data["earnings"] = _earnings_to_list(earnings)
    if "ownership" in panels:
        data["ownership"] = _optional_to_dict(ownership)
    if "bandar" in panels:
        data["bandar"] = _optional_to_dict(bandar)
    if "foreign_flow" in panels:
        data["foreign_flow"] = _flow_points_summary(
            foreign_flow_points, source=foreign_flow_source
        )
    if "corp_actions" in panels:
        data["corp_actions"] = [_optional_to_dict(e) for e in corp_actions]
    if "insider" in panels:
        data["insider"] = {
            "transactions": [_optional_to_dict(t) for t in insider_txns[:20]],
            "last_known_outside_window": (
                insider_last_known.isoformat() if insider_last_known else None
            ),
        }
    if "seasonality" in panels:
        data["seasonality"] = _optional_to_dict(seasonality)
    if "iev" in panels:
        data["iev"] = [_optional_to_dict(r) for r in iev_rows[:10]]
    if "sentiment" in panels:
        data["sentiment"] = [_optional_to_dict(s) for s in sentiment_logs[:20]]
    if "profile" in panels:
        data["profile"] = _optional_to_dict(profile)
    if "candles" in panels:
        data["candles"] = _candles_to_list(candles, limit=5)

    return payload
