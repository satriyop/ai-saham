"""
Corporate actions and news sentiment panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _empty_state_text, _not_cached
from src.adapters.cli.view_ticker_status import CacheStatus
from src.application.services.ticker_dashboard_corp_actions import (
    calendar_event_to_display as _calendar_event_to_display,
)
from src.application.services.ticker_dashboard_corp_actions import (
    merge_corp_action_events as _merge_corp_action_events,
)
from src.application.use_case.get_ticker_dashboard_use_case import (
    CORP_ACTION_LOOKAHEAD_DAYS,
    CORP_ACTION_LOOKBACK_DAYS,
)

CORP_ACTION_PANEL_TITLE = "Corporate Actions (12m)"

# Re-export for older tests/callers.
__all__ = [
    "CORP_ACTION_LOOKAHEAD_DAYS",
    "CORP_ACTION_LOOKBACK_DAYS",
    "CORP_ACTION_PANEL_TITLE",
    "_calendar_event_to_display",
    "_corp_action_panel",
    "_merge_corp_action_events",
    "_sentiment_panel",
]


def _corp_action_panel(
    events: list,
    *,
    status: CacheStatus = CacheStatus.EMPTY,
    last_known=None,
    empty_hint: str | None = None,
) -> object:
    events_sorted = [e for e in events if getattr(e, "event_type", None) != "__NONE__"]
    if not events_sorted:
        return panel(
            _empty_state_text(
                status,
                window_label="last 12 months",
                last_known=last_known,
                hint=empty_hint,
            ),
            title=CORP_ACTION_PANEL_TITLE,
        )

    tbl = compact_table()
    tbl.add_column("Type", style="dim", min_width=10)
    tbl.add_column("Ex-date", min_width=11)
    tbl.add_column("Cum", min_width=11, style="dim")
    tbl.add_column("Detail")
    tbl.add_column("Status", min_width=8)

    for e in events_sorted[:8]:
        status_style = "green" if e.status == "active" else "dim"
        tbl.add_row(
            e.event_type.replace("_", " ").title(),
            str(e.ex_date) if e.ex_date else "\u2014",
            str(e.cum_date) if e.cum_date else "\u2014",
            e.detail or "\u2014",
            Text(e.status or "\u2014", style=status_style),
        )

    return panel(tbl, title=CORP_ACTION_PANEL_TITLE)


def _sentiment_panel(logs: list, *, empty_hint: str | None = None) -> object:
    if not logs:
        return panel(_not_cached(hint=empty_hint), title="News Sentiment")

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Sentiment", min_width=10)
    tbl.add_column("Catalyst", style="dim")
    tbl.add_column("Score", justify="right", min_width=5, style="dim")

    _SENTIMENT_STYLE = {"POSITIVE": "green", "NEGATIVE": "red", "NEUTRAL": "yellow"}

    for log in logs[:8]:
        style = _SENTIMENT_STYLE.get(log.sentiment.value, "default")
        tbl.add_row(
            str(log.date),
            Text(log.sentiment.value.title(), style=style),
            log.catalyst.value.replace("_", " ").title() if log.catalyst else "\u2014",
            f"{log.score:.2f}",
        )

    return panel(tbl, title="News Sentiment")
