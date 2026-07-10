"""
Display/formatting helpers for `saham fetch market` output.

Pure rendering of already-computed status strings and status DTOs into
terminal output. Does not fetch data, call providers, load configs, or
decide cache/freshness policy.

Layer: Adapter
"""

import re
from datetime import date
from pathlib import Path

import typer

from src.infrastructure.persistence.sqlite_data_update_status import (
    build_data_update_table_statuses,
)


def _fmt_status(s: str) -> str:
    """Map internal status strings to concise display labels."""
    for prefix in ("agg=up-to-date(", "daily=up-to-date(", "up-to-date("):
        if s.startswith(prefix):
            tag = prefix[: prefix.index("up-to-date(")]  # "" | "agg=" | "daily="
            date_part = s[len(prefix):-1]
            return f"{tag}✓({date_part})"
    return s


def clean_row_span(s: str) -> str:
    # Remove up-to-date prefix
    s = _fmt_status(s)
    # Replace backfill+Nrows/span=Kd -> bf+Nr(Kd)
    s = re.sub(r'backfill\+(\d+)rows/span=(\d+)d', r'bf+\1r(\2d)', s)
    # Replace +Nrows/span=Kd -> +Nr(Kd)
    s = re.sub(r'\+(\d+)rows/span=(\d+)d', r'+\1r(\2d)', s)
    # Replace refreshed/span=Kd -> ref(Kd)
    s = re.sub(r'refreshed/span=(\d+)d', r'ref(\1d)', s)
    return s


def split_flow_parts(flow_str: str) -> tuple[str, str]:
    daily_part = "skip"
    agg_part = "skip"

    # Extract daily part
    daily_match = re.search(r'(daily=✓\([^)]+\)|daily=[^ ]+|daily:\+[^ ]+)', flow_str)
    if daily_match:
        daily_part = daily_match.group(1)

    # Extract agg part
    agg_match = re.search(r'(agg=✓\([^)]+\)|agg=[^ ]+|agg:\+[^ ]+)', flow_str)
    if agg_match:
        agg_part = agg_match.group(1)

    # If it's a fallback single status (e.g. no daily or agg keys, like "✓(2026-06-19)" or "skip" or "ERR:...")
    if not daily_match and not agg_match:
        if "ERR:" in flow_str:
            return flow_str, flow_str
        return flow_str, flow_str

    return daily_part, agg_part


def fmt_tracked_flow_column(daily_part: str) -> str:
    s = _fmt_status(daily_part)
    s = re.sub(r'\b\d{4}-', '', s)
    s = re.sub(r'daily=✓\(([^)]+)\)', r'✓(\1)', s)
    s = re.sub(r'daily=✓', '✓', s)
    s = re.sub(r'daily:\+(\d+)rows/\d+codes/(\d+)d', r'+\1r(\2d)', s)
    s = re.sub(r'daily:\+(\d+)rows/(\d+)d', r'+\1r(\2d)', s)
    s = re.sub(r'daily:', '', s)
    return s


def fmt_inst_flow_column(agg_part: str) -> str:
    s = _fmt_status(agg_part)
    s = re.sub(r'\b\d{4}-', '', s)
    s = re.sub(r'agg=✓\(([^)]+)\)', r'✓(\1)', s)
    s = re.sub(r'agg=✓', '✓', s)
    s = re.sub(r'agg:\+(\d+)rows/(\d+)d', r'+\1r(\2d)', s)
    s = re.sub(r'agg:', '', s)
    return s


def fmt_meta_column(s: str) -> str:
    # E.g. "new(Financial Services)" or "cached(5d)" or "skip"
    if len(s) <= 18:
        return s

    match = re.match(r'(\w+)\((.+)\)', s)
    if match:
        prefix, content = match.groups()
        # Truncate content so total length is 18
        max_content_len = 18 - len(prefix) - 2  # -2 for "(" and ")"
        if max_content_len > 3:
            truncated = content[:max_content_len-2] + ".."
            return f"{prefix}({truncated})"
    return s[:18]


def fmt_enrichment_column(s: str) -> str:
    # E.g. "✓(notation,analyst,insider,season,corp,holding,bandar,fundam,fwd_est,profile)"
    # or "notation+analyst  ✓(insider,season,corp,holding,bandar,fundam,fwd_est,profile)"
    # or "ERR:insider:Playwright error,corp:timeout"
    # or "skip"
    if s == "skip":
        return "skip"

    if s.startswith("ERR:"):
        errors_part = s[4:]
        err_tokens = errors_part.split(",")
        err_labels = []
        for token in err_tokens:
            parts = token.split(":")
            if parts:
                err_labels.append(parts[0])
        failed_count = len(err_labels)
        success_count = max(0, 10 - failed_count)
        return f"{success_count}/10 (ERR: {', '.join(err_labels)})"

    fetched_part = ""
    cached_part = ""

    if "  ✓(" in s:
        parts = s.split("  ✓(")
        fetched_part = parts[0].strip()
        cached_part = parts[1].rstrip(")")
    elif s.startswith("✓("):
        cached_part = s[2:].rstrip(")")
    else:
        fetched_part = s.strip()

    fetched_list = [x for x in fetched_part.split("+") if x]
    cached_list = [x for x in cached_part.split(",") if x]

    fetched_count = len(fetched_list)
    cached_count = len(cached_list)
    total_count = fetched_count + cached_count

    if total_count == 0:
        return s

    if fetched_count == 0:
        return f"{total_count}/{total_count} ✓"

    if fetched_count <= 2:
        return f"{total_count}/{total_count} (+{fetched_count}: {', '.join(fetched_list)})"
    return f"{total_count}/{total_count} (+{fetched_count})"


def echo_note_group(
    title: str,
    messages: list[str],
    color: str,
    limit: int = 12,
    footer: str | None = None,
) -> None:
    """Print a compact note group without flooding large universe updates."""
    if not messages:
        return
    typer.echo("")
    typer.echo(typer.style(title, fg=color))
    for msg in messages[:limit]:
        typer.echo(typer.style(msg, fg=color))
    remaining = len(messages) - limit
    if remaining > 0:
        typer.echo(typer.style(f"  ... {remaining} more", fg=color))
    if footer:
        typer.echo(typer.style(footer, fg=color))


def print_table_summary(
    db_path: Path,
    stock_tickers: list[str],
    candles_provider: str,
    broker_provider_name: str,
    no_meta: bool,
    candles_only: bool,
    broker_only: bool,
    expected_trading_day: date,
    enrichment_available: bool = False,
    market_is_open: bool = False,
) -> None:
    """Print a dynamic post-run database status for tables touched by update."""
    try:
        statuses = build_data_update_table_statuses(
            db_path=db_path,
            tickers=stock_tickers,
            candles_provider=candles_provider,
            broker_provider_name=broker_provider_name,
            no_meta=no_meta,
            candles_only=candles_only,
            broker_only=broker_only,
            enrichment_available=enrichment_available,
            expected_trading_day=expected_trading_day,
            market_is_open=market_is_open,
        )
    except Exception as e:
        typer.echo("")
        typer.echo(typer.style(f"Database status unavailable: {str(e)[:80]}", fg=typer.colors.YELLOW))
        return

    W = 140
    prefix_width = 95
    impact_width = W - prefix_width
    typer.echo(f"\n{'─' * W}")
    typer.echo("  Database status after command (scoped to this run's stock tickers)")
    typer.echo(f"{'─' * W}")
    typer.echo(f"  {'TABLE':<24} {'SOURCE':<16} {'ROWS':>8} {'TICKERS':>7} {'RANGE/FRESH':<23} {'STATUS':<9} IMPACT")
    typer.echo(f"{'─' * W}")

    issues: list[str] = []
    for status in statuses:
        rows = "-" if status.rows is None else f"{status.rows:,}"
        tickers = "-" if status.tickers is None else f"{status.tickers:,}"
        color = typer.colors.GREEN
        if status.status in {"skipped", "n/a"}:
            color = typer.colors.BRIGHT_BLACK
        elif status.status == "pending-eod":
            color = typer.colors.CYAN
        elif status.status in {"partial", "stale", "empty", "missing", "missing-db"}:
            color = typer.colors.YELLOW
        prefix = (
            f"  {status.table:<24} {status.source:<16} {rows:>8} {tickers:>7} "
            f"{status.range_label:<23} {status.status:<9}"
        )
        if len(status.impact) <= impact_width:
            typer.echo(typer.style(f"{prefix} {status.impact}", fg=color))
        else:
            typer.echo(typer.style(prefix, fg=color))
            typer.echo(typer.style(f"  {'':<{prefix_width - 2}}{status.impact}", fg=color))
        if status.issue and status.status != "pending-eod":
            issues.append(f"  {status.table}: {status.issue}")

    typer.echo(f"{'─' * W}")
    typer.echo(f"  Rows/tickers are totals for the {len(stock_tickers)} stock ticker(s) in this run.")
    if issues:
        echo_note_group(
            title=f"Database issues/impact ({len(issues)}):",
            messages=issues,
            color=typer.colors.YELLOW,
            footer="   Update succeeded unless a fetch error was listed above; incomplete optional caches are warnings.",
        )


def render_enrichment_pit_coverage(coverage) -> None:
    """Print a per-table PIT coverage summary to stdout."""
    w = 26
    typer.echo("\nPoint-in-time enrichment coverage:")
    typer.echo(f"  {'TABLE':<{w}} {'SNAPSHOTS':>10} {'LATEST':>12} {'TICKERS (LATEST)':>18}")
    typer.echo(f"  {'─'*w} {'─'*10} {'─'*12} {'─'*18}")
    for row in coverage:
        typer.echo(
            f"  {row.table:<{w}} {row.snapshot_count:>10} "
            f"{str(row.latest_date or 'n/a'):>12} {row.tickers_in_latest:>18}"
        )
    typer.echo("")
    typer.echo(
        "Note: Stockbit returns current values only — no historical API exists. "
        "Observations before the first snapshot will have UNKNOWN market_cap_bucket "
        "and enrichment fields. Run this command periodically to build a PIT history."
    )
