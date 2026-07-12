"""
Corporate actions and news sentiment panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _not_cached


def _corp_action_panel(events: list) -> object:
    if not events:
        return panel(_not_cached(), title="Corporate Actions")

    events_sorted = sorted(
        [e for e in events if e.event_type != "__NONE__"],
        key=lambda e: (e.ex_date or e.cum_date or e.announcement_date or date.min),
        reverse=True,
    )
    if not events_sorted:
        return panel(_not_cached(), title="Corporate Actions")

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

    return panel(tbl, title="Corporate Actions")


def _sentiment_panel(logs: list) -> object:
    if not logs:
        return panel(_not_cached(), title="News Sentiment")

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
