"""Optional analysis evidence panels for screen accum judgment desk (ADR-054 S1).

Renders side-bag evidence only. Does not re-score Action or show structure/lots.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any, Mapping

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.services.screen_judgment_deep_evidence import (
    ScreenJudgmentDeepEvidence,
    ScreenJudgmentDeepEvidenceRequest,
)


def print_screen_deep_evidence_panels(
    *,
    deep_evidence_by_ticker: Mapping[str, ScreenJudgmentDeepEvidence],
    deep_flags: ScreenJudgmentDeepEvidenceRequest | None,
    candidates: list[Any],
) -> None:
    """Print analysis evidence after judgment panels (explicit tickers only)."""
    if not deep_evidence_by_ticker:
        return
    flags = deep_flags or ScreenJudgmentDeepEvidenceRequest()
    if not flags.any_enabled:
        return

    for candidate in candidates:
        ticker = str(getattr(candidate, "ticker", "")).upper()
        bag = deep_evidence_by_ticker.get(ticker)
        if bag is None:
            continue
        _print_one(bag=bag, flags=flags)


def _print_one(
    *,
    bag: ScreenJudgmentDeepEvidence,
    flags: ScreenJudgmentDeepEvidenceRequest,
) -> None:
    console().print("")
    console().print(
        Text(
            f"Analysis evidence · {bag.ticker} (diagnostic · does not change Action)",
            style="bold cyan",
        )
    )

    if bag.setup_name and bag.setup_eval is not None:
        _print_setup_lens(bag)
    elif bag.setup_name:
        console().print(
            panel(
                Text(f"Setup lens '{bag.setup_name}': not available", style="dim"),
                title="Setup lens",
            )
        )

    if flags.wants_flow:
        _print_flow(bag)

    if flags.wants_sentiment:
        _print_sentiment(bag, flags.sentiment_verbose)

    if flags.wants_strategy:
        _print_strategy(bag)

    if bag.warnings:
        for w in bag.warnings:
            console().print(Text(f"  ⚠ {w}", style="yellow"))

    console().print(
        Text(
            f"Structure (lots / SL / TP): saham plan swing {bag.ticker} --capital <IDR>",
            style="dim",
        )
    )


def _print_setup_lens(bag: ScreenJudgmentDeepEvidence) -> None:
    ev = bag.setup_eval
    match = getattr(getattr(ev, "match", None), "value", str(getattr(ev, "match", "?")))
    table = compact_table(show_header=True)
    table.add_column("Gate")
    table.add_column("Pass")
    table.add_column("Actual")
    table.add_column("Required")
    for gate in getattr(ev, "gates", ()) or ():
        table.add_row(
            str(getattr(gate, "label", "")),
            "yes" if getattr(gate, "passed", False) else "no",
            str(getattr(gate, "actual", "")),
            str(getattr(gate, "required", "")),
        )
    failed = getattr(ev, "failed_reasons", ()) or ()
    footer = Text(
        f"match={match} · MATCH ≠ ENTER (ADR-031)",
        style="dim",
    )
    if failed:
        footer = Group(
            footer,
            Text("failed: " + "; ".join(str(r) for r in failed), style="yellow"),
        )
    console().print(
        panel(
            Group(Text(f"Setup: {bag.setup_name}", style="bold"), table, footer),
            title="Setup lens (diagnostic)",
        )
    )


def _print_flow(bag: ScreenJudgmentDeepEvidence) -> None:
    fd = bag.flow_detail
    if fd is None:
        console().print(panel(Text("Flow detail unavailable", style="dim"), title="Flow detail"))
        return
    table = compact_table(show_header=False)
    table.add_column("K", style="bold cyan")
    table.add_column("V")
    table.add_row("Window", str(getattr(fd, "window_sessions", "—")))
    table.add_row("Sessions", str(getattr(fd, "available_sessions", "—")))
    table.add_row(
        "Buy / sell sessions",
        f"{getattr(fd, 'buy_sessions', '—')} / {getattr(fd, 'sell_sessions', '—')}",
    )
    table.add_row("Consec buy", str(getattr(fd, "consecutive_buy_sessions", "—")))
    table.add_row("Total net flow", str(getattr(fd, "total_net_flow", "—")))
    table.add_row("Latest net", str(getattr(fd, "latest_net_flow", "—")))
    avg = getattr(fd, "avg_flow_ratio_pct", None)
    table.add_row("Avg flow ratio %", f"{avg:.2f}" if isinstance(avg, (int, float)) else "—")
    console().print(panel(table, title="Flow detail"))


def _print_sentiment(bag: ScreenJudgmentDeepEvidence, verbose: bool) -> None:
    resp = bag.sentiment_response
    warning = bag.sentiment_warning
    lines: list[Text] = []
    if resp is not None and not getattr(resp, "warning", None):
        snap = getattr(resp, "snapshot", None)
        if snap is not None:
            overall = getattr(getattr(snap, "overall_sentiment", None), "value", "?")
            lines.append(Text(f"Call: {str(overall).upper()}", style="bold"))
            lines.append(
                Text(
                    f"Headlines: {getattr(snap, 'total_count', '?')} "
                    f"(+{getattr(snap, 'positive_count', '?')} / "
                    f"={getattr(snap, 'neutral_count', '?')} / "
                    f"-{getattr(snap, 'negative_count', '?')}) | "
                    f"conf {getattr(snap, 'confidence_pct', '?')}%"
                )
            )
        else:
            lines.append(Text("Sentiment snapshot empty", style="dim"))
    else:
        msg = warning or getattr(resp, "warning", None) or "News unavailable"
        lines.append(Text(str(msg), style="dim"))
        if not verbose:
            lines.append(Text("Use --sentiment-verbose for provider details.", style="dim italic"))
    console().print(panel(Group(*lines), title="Sentiment evidence"))


def _print_strategy(bag: ScreenJudgmentDeepEvidence) -> None:
    bt = bag.backtest_result
    if bt is None:
        console().print(
            panel(
                Text("Strategy backtest evidence unavailable", style="dim"),
                title="Strategy evidence",
            )
        )
        return
    table = compact_table(show_header=False)
    table.add_column("K", style="bold cyan")
    table.add_column("V")
    for key in (
        "total_trades",
        "win_rate",
        "profit_factor",
        "max_drawdown_pct",
        "expectancy",
    ):
        if hasattr(bt, key):
            table.add_row(key, str(getattr(bt, key)))
    # Fall back to a few common attributes on result wrappers
    for key in ("trades", "metrics", "summary"):
        if hasattr(bt, key) and key not in ("total_trades",):
            val = getattr(bt, key)
            if val is not None and not callable(val):
                table.add_row(key, str(val)[:120])
                break
    console().print(
        panel(
            Group(
                table,
                Text("Evidence only — does not set Action.", style="dim"),
            ),
            title="Strategy evidence",
        )
    )
