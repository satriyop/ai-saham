"""
Sentiment evidence panel for saham analyze swing full output.

Layer: Adapter

Renders the news sentiment snapshot or provider-unavailable status. Does
not compute business action.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.analyze_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.rich_display import console, panel


def print_sentiment_evidence_panel(ctx: SwingOutputDisplayContext) -> None:
    if not ctx.options.include_sentiment:
        return

    sentiment_resp = ctx.evidence.sentiment_response
    sentiment_warning = ctx.evidence.sentiment_warning
    sentiment_verbose = ctx.options.sentiment_verbose

    sentiment_group = []
    if sentiment_resp and not sentiment_resp.warning:
        snap = sentiment_resp.snapshot
        call_val = snap.overall_sentiment.value.upper()
        call_style = "green" if call_val == "POSITIVE" else ("red" if call_val == "NEGATIVE" else "yellow")

        _sentiment_label = Text("News Sentiment (3d): ", style="bold cyan")
        _sentiment_label.append(call_val, style=call_style)
        sentiment_group.append(_sentiment_label)
        sentiment_group.append(Text(
            f"Headlines scanned: {snap.total_count} (+{snap.positive_count} / ={snap.neutral_count} / -{snap.negative_count}) | "
            f"Confidence: {snap.confidence_pct}%"
        ))
    else:
        sentiment_group.append(Text("News Sentiment (3d)", style="bold cyan"))
        msg = sentiment_warning or "News unavailable (no network or fetch failed)."
        sentiment_group.append(Text(msg, style="dim"))
        if not sentiment_verbose:
            sentiment_group.append(Text("Use --sentiment-verbose to show provider details.", style="dim italic"))

    console().print("")
    console().print(
        panel(
            Group(*sentiment_group),
            title="SENTIMENT EVIDENCE",
        )
    )
