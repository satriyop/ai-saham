"""
CLI commands for market data acquisition + status.

Commands (all under `saham data`):
  saham data update [TICKERS]   — fetch candles + broker flow
  saham data broker …           — broker flow management (sub-group)
  saham data stockbit …         — Stockbit session management (sub-group)
  saham data universe …         — stock universe lists (sub-group)
  saham data status             — check provider health + data freshness

Layer: Adapter
"""

import os
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import typer

from src.adapters.cli.update_commands import update
from src.adapters.cli.broker_commands import broker_app
from src.adapters.cli.stockbit_commands import stockbit_app
from src.adapters.cli.accumulation_commands import universe_app

data_app = typer.Typer(
    name="data",
    help="Market data — fetch candles, broker flow, and universe lists.",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")

data_app.command("update")(update)
data_app.add_typer(broker_app, name="broker")
data_app.add_typer(stockbit_app, name="stockbit")
data_app.add_typer(universe_app, name="universe")


# ── Status helpers ──────────────────────────────────────────────────────────

_ICON_OK = typer.style(" ✅", fg=typer.colors.GREEN, bold=True)
_ICON_WARN = typer.style(" ⚠", fg=typer.colors.YELLOW, bold=True)
_ICON_FAIL = typer.style(" ✗", fg=typer.colors.RED, bold=True)

# Total visual width for boxes
_W = 80


def _check_idx_api() -> dict:
    """Probe IDX GetStockSummary endpoint. Returns status dict."""
    from src.infrastructure.data_providers.idx import (
        IDX_API_BASE,
        IDX_HEADERS,
        STOCK_SUMMARY_ENDPOINT,
    )
    import httpx

    target = date.today() - timedelta(days=1)
    url = f"{IDX_API_BASE}{STOCK_SUMMARY_ENDPOINT}"
    params = {"start": 0, "length": 1, "date": target.strftime("%Y%m%d")}

    start = time.time()
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params=params, headers=IDX_HEADERS, follow_redirects=True)
        elapsed = round(time.time() - start, 1)

        if resp.status_code == 200:
            data = resp.json().get("data", [])
            return {"ok": True, "label": f"200 ({len(data)} stocks)", "ms": elapsed}
        elif resp.status_code == 403:
            return {"ok": True, "label": "403 (non-trading day)", "ms": elapsed}
        else:
            return {"ok": False, "label": f"HTTP {resp.status_code}", "ms": elapsed}
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {"ok": False, "label": str(e)[:55], "ms": elapsed}


def _check_yahoo() -> dict:
    """Probe Yahoo Finance ^JKSE. Returns status dict."""
    import yfinance as yf

    start = time.time()
    try:
        hist = yf.download("^JKSE", period="5d", progress=False, auto_adjust=True)
        elapsed = round(time.time() - start, 1)

        if hist is not None and not hist.empty:
            return {"ok": True, "label": f"{len(hist)} days (^JKSE)", "ms": elapsed}
        return {"ok": True, "label": "empty response", "ms": elapsed}
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {"ok": False, "label": str(e)[:55], "ms": elapsed}


def _check_stockbit_session() -> dict:
    """Check Stockbit session without opening a browser."""
    try:
        from src.infrastructure.browser.playwright_stockbit import get_session_status

        start = time.time()
        info = get_session_status()
        elapsed = round(time.time() - start, 1)

        if not info.get("exists"):
            return {"ok": False, "label": "no session found", "ms": elapsed}

        likely = info.get("likely_valid", False)
        age = info.get("age_hours")
        age_str = f" ({age}h old)" if age is not None else ""
        if likely:
            return {"ok": True, "label": f"valid{age_str}", "ms": elapsed}
        return {"ok": False, "label": f"expired{age_str}", "ms": elapsed}
    except ImportError:
        return {"ok": False, "label": "playwright not installed", "ms": 0}
    except Exception as e:
        return {"ok": False, "label": str(e)[:55], "ms": 0}


def _check_ai_api() -> dict:
    """Check if AI API keys are configured."""
    configured = []
    if os.environ.get("DEEPSEEK_API_KEY"):
        configured.append("DeepSeek")
    if os.environ.get("ANTHROPIC_API_KEY"):
        configured.append("Claude")
    if os.environ.get("OPENAI_API_KEY"):
        configured.append("OpenAI")
    if os.environ.get("GEMINI_API_KEY"):
        configured.append("Gemini")

    if not configured:
        return {"ok": False, "label": "no API key (set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY)"}
    return {"ok": True, "label": f"{', '.join(configured)} key(s) set", "ms": 0}


def _health_line(name: str, result: dict) -> str:
    """Format a health check line."""
    icon = _ICON_OK if result["ok"] else (_ICON_WARN if "key" in result.get("label", "") or "expired" in result.get("label", "") else _ICON_FAIL)
    ms = result.get("ms", 0)
    ms_str = f"{ms}s" if ms else ""
    label = result.get("label", "?")
    return f"  │ {name:<18s} {icon}  {label:<52s} {ms_str:>6s} │"


# ── Status command ──────────────────────────────────────────────────────────

@data_app.command("status")
def status(
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH, "--db", help="Path to SQLite database",
    ),
) -> None:
    """
    Check data provider health and database freshness.

    Probes IDX API, Yahoo Finance, Stockbit session, and AI classifier.
    Reports latest data dates and row counts across all database tables.
    """
    C = _W - 4  # content width inside │ │ (indent 2 each side)

    typer.echo("")
    typer.echo("  ╭─ Data Provider Health " + "─" * (C - 23) + "╮")
    typer.echo(_health_line("IDX API", _check_idx_api()))
    typer.echo(_health_line("Yahoo Finance", _check_yahoo()))
    typer.echo(_health_line("Stockbit session", _check_stockbit_session()))
    typer.echo(_health_line("AI classifier", _check_ai_api()))
    typer.echo("  ╰" + "─" * C + "╯")
    typer.echo("")

    _show_data_freshness(db_path)


def _show_data_freshness(db_path: Path) -> None:
    """Query DB and display data freshness table."""
    C = _W - 4  # content width inside │ │ (indent 2 each side)

    if not db_path.exists():
        typer.echo("  ╭─ Data Freshness " + "─" * (C - 17) + "╮")
        typer.echo(f"  │  No database at {str(db_path):<{C - 7}s} │")
        typer.echo(f"  │  Run: saham data update <TICKER>{' ' * (C - 34)} │")
        typer.echo("  ╰" + "─" * C + "╯")
        return

    queries = [
        ("broker_summaries", "SELECT source, MAX(date), COUNT(*) FROM broker_summaries GROUP BY source"),
        ("foreign_flow_points", "SELECT source, MAX(date), COUNT(*) FROM foreign_flow_points GROUP BY source"),
        ("broker_daily_flow", "SELECT source, MAX(date), COUNT(*) FROM broker_daily_flow GROUP BY source"),
        ("candles", "SELECT '—', MAX(date), COUNT(*) FROM candles"),
    ]

    rows: list[dict] = []
    try:
        conn = sqlite3.connect(str(db_path))
        for table, sql in queries:
            try:
                for row in conn.execute(sql).fetchall():
                    rows.append({
                        "table": table,
                        "source": row[0],
                        "latest": row[1],
                        "count": row[2],
                    })
            except sqlite3.OperationalError:
                pass
        conn.close()
    except sqlite3.OperationalError as e:
        typer.echo(f"  DB error: {e}")
        return

    if not rows:
        typer.echo("  No data found.")
        return

    _print_freshness_table(rows)


def _print_freshness_table(rows: list[dict]) -> None:
    """Print a formatted freshness table with age warnings."""
    today = date.today()
    C = _W - 4  # content width inside │ │

    typer.echo("  ╭─ Data Freshness " + "─" * (C - 17) + "╮")
    typer.echo(f"  │ {'TABLE':<22s} {'SOURCE':<12s} {'LATEST':<14s} {'ROWS':>8s}  {'STATUS':<16s} │")
    typer.echo("  │ " + "─" * (C - 2) + " │")

    for r in sorted(rows, key=lambda x: (x["table"], x["source"])):
        latest_str = r["latest"] or "—"
        count_str = f"{r['count']:,}" if r["count"] else "0"

        stale = False
        if r["latest"]:
            try:
                dt = datetime.strptime(r["latest"], "%Y-%m-%d").date()
                days_behind = (today - dt).days
                stale = days_behind > 5
            except ValueError:
                days_behind = 0
        else:
            days_behind = 999

        if stale:
            status = typer.style(f"⚠ {days_behind}d behind", fg=typer.colors.YELLOW)
        elif days_behind == 0 and r["latest"]:
            status = typer.style("✓ today", fg=typer.colors.GREEN)
        elif days_behind == 1:
            status = typer.style("✓ yesterday", fg=typer.colors.GREEN)
        elif days_behind <= 5:
            status = typer.style("✓ current", fg=typer.colors.GREEN)
        else:
            status = typer.style("—", fg=typer.colors.BRIGHT_BLACK)

        typer.echo(f"  │ {r['table']:<22s} {r['source']:<12s} {latest_str:<14s} {count_str:>8s}  {status:<16s} │")

    typer.echo("  ╰" + "─" * C + "╯")
