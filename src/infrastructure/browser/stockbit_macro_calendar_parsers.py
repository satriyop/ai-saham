"""
Stockbit economic calendar parsers — pure parse helpers for
GET /corpaction/economic into MacroCalendarEvent value objects.

Layer: Infrastructure
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from typing import Any

from src.domain.value_objects.macro_calendar_event import MacroCalendarEvent
from src.infrastructure.config.macro_calendar_config import (
    MacroCalendarConfig,
    load_macro_calendar_config,
    normalize_macro_category,
)

logger = logging.getLogger(__name__)


def _fallback_id(event_date: str, title: str, raw: dict) -> str:
    """Deterministic id when econcal_id is missing. Never uses hash()."""
    composite = f"economic|{event_date}|{title}|{json.dumps(raw, sort_keys=True, default=str)}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()


def _parse_date(raw: object) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _opt_str(raw: object) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def parse_economic_item(
    item: dict[str, Any],
    *,
    fetched_at: str,
    timezone: str | None = None,
    category_config: MacroCalendarConfig | None = None,
) -> MacroCalendarEvent | None:
    """Parse one economic[] row. Returns None for unusable rows (skip, do not fail batch)."""
    if not isinstance(item, dict):
        return None

    title = _opt_str(item.get("econcal_item"))
    event_date = _parse_date(item.get("econcal_date"))
    if not title or event_date is None:
        logger.warning(
            "Skipping economic calendar row missing title/date: keys=%s",
            list(item.keys()),
        )
        return None

    source_id = _opt_str(item.get("econcal_id"))
    if not source_id:
        source_id = _fallback_id(event_date.isoformat(), title, item)

    category = normalize_macro_category(title, category_config)

    return MacroCalendarEvent(
        source_event_id=source_id,
        event_date=event_date,
        category=category,
        title=title,
        event_time=_opt_str(item.get("econcal_time")),
        timezone=timezone,
        country="ID",
        actual=_opt_str(item.get("econcal_actual")),
        previous=_opt_str(item.get("econcal_previous")),
        forecast=_opt_str(item.get("econcal_forecast")),
        reference_period=_opt_str(item.get("econcal_month")),
        source="stockbit",
        raw_payload_json=json.dumps(item, sort_keys=True, default=str),
        fetched_at=fetched_at,
    )


def parse_economic_body(
    body: dict[str, Any],
    *,
    fetched_at: str,
    category_config: MacroCalendarConfig | None = None,
) -> list[MacroCalendarEvent]:
    """Parse a full Stockbit economic calendar response body."""
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        # Some responses may put economic at top level — still fail closed if missing.
        if isinstance(body, dict) and isinstance(body.get("economic"), list):
            data = body
        else:
            raise ValueError("economic calendar body missing data object")

    items = data.get("economic")
    if items is None:
        raise ValueError("economic calendar body missing data.economic list")
    if not isinstance(items, list):
        raise ValueError("data.economic must be a list")

    tz_raw = data.get("timezone")
    timezone = _opt_str(tz_raw) if tz_raw is not None else None
    # Stockbit sometimes returns timezone as int (offset hours) — store as string.
    if timezone is None and "timezone" in data and data["timezone"] is not None:
        timezone = str(data["timezone"])

    cfg = category_config if category_config is not None else load_macro_calendar_config()
    events: list[MacroCalendarEvent] = []
    for item in items:
        parsed = parse_economic_item(
            item if isinstance(item, dict) else {},
            fetched_at=fetched_at,
            timezone=timezone,
            category_config=cfg,
        )
        if parsed is not None:
            events.append(parsed)
    return events
