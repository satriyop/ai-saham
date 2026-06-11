"""
CLI commands for foreign accumulation screening and universe management.

Commands:
  saham screen accumulation — scan stocks for foreign accumulation patterns
  saham universe list       — show configured ticker universes
  saham universe update     — refresh universe lists from IDX (future)

Layer: Adapter
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import (
    UniverseNotFoundError,
    load_universe_meta,
    resolve_tickers,
)
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenResponse,
    AccumulationScreenUseCase,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

accumulation_app = typer.Typer(
    name="accumulation",
    help="Foreign accumulation screener",
    no_args_is_help=True,
)

universe_app = typer.Typer(
    name="universe",
    help="Manage stock universe lists (LQ45, IDX80, IDXComp100)",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")

# Table widths
_TABLE_WIDTH = 93
_SEP_WIDTH = 91


def _format_value(value: Decimal) -> str:
    """Format large IDR values with T/B/M suffix."""
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.0f}M"
    return f"{sign}{abs_v:.0f}"


def _fmt_score(s: float | None) -> str:
    """Format a score with color for table cells."""
    if s is None:
        return typer.style("   —  ", fg=typer.colors.BRIGHT_BLACK)
    if s >= 70:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.GREEN)
    if s >= 40:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:>6.1f}", fg=typer.colors.WHITE)


def _classify_pattern(
    windows: list[int],
    candidates_by_window: dict[int, "AccumulationCandidate | None"],
) -> str:
    """Label the multi-window pattern for a ticker."""
    threshold = 60.0
    hot = [w for w in windows if candidates_by_window.get(w) and candidates_by_window[w].score >= threshold]

    # Coiled spring: any window with squeeze + strong score
    for w in windows:
        c = candidates_by_window.get(w)
        if c and c.score >= threshold and c.bb_width_pctile is not None and c.bb_width_pctile <= 0.20:
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"


def _display_results(
    response: AccumulationScreenResponse,
    universe_label: str,
    top_n: int,
    granular: bool,
    vwap_only: bool,
    squeeze_only: bool,
    show_breakdown: bool,
) -> None:
    """Render accumulation screener results as terminal table."""
    candidates = response.candidates
    if vwap_only:
        candidates = [c for c in candidates if c.vwap_discount_pct and c.vwap_discount_pct > 0]
    if squeeze_only:
        candidates = [c for c in candidates if c.bb_width_pctile is not None and c.bb_width_pctile <= 0.20]

    candidates = candidates[:top_n]

    typer.echo("")
    typer.echo("=" * _TABLE_WIDTH)
    typer.echo(
        f"FOREIGN ACCUMULATION — {universe_label.upper()} "
        f"| {response.window_days}d window | {response.screened_at}"
    )
    typer.echo("=" * _TABLE_WIDTH)

    if not candidates:
        typer.echo("No candidates found matching the criteria.")
        typer.echo(
            f"Checked {response.total_tickers_checked} tickers, "
            f"skipped {response.tickers_skipped} (insufficient data)."
        )
        typer.echo("=" * _TABLE_WIDTH)
        return

    header = (
        f"{'#':>3} {'TICKER':<7} {'SCORE':>6} {'STREAK':>7} {'NET_DAYS':>9}"
        f" {'NET_VALUE':>12} {'FLOW%':>6} {'VWAP_DISC':>10} {'RSI':>6} {'BB%ILE':>7} {'TREND':>5}"
    )
    typer.echo(header)
    typer.echo("-" * _SEP_WIDTH)

    for i, c in enumerate(candidates, 1):
        net_days_str = f"{c.net_buy_days}/{c.total_days}"
        vwap_str = f"{c.vwap_discount_pct:+.1f}%" if c.vwap_discount_pct is not None else "    —  "
        rsi_str = f"{c.rsi:.1f}" if c.rsi is not None else "  —"
        streak_str = f"{c.consecutive_streak}d"
        flow_str = f"{c.avg_flow_ratio:+.1f}" if c.avg_flow_ratio is not None else "   —"
        if c.bb_width_pctile is not None:
            pct_int = int(c.bb_width_pctile * 100)
            bb_color = typer.colors.GREEN if c.bb_width_pctile <= 0.20 else (
                typer.colors.YELLOW if c.bb_width_pctile <= 0.40 else typer.colors.WHITE
            )
            bb_str = typer.style(f"{pct_int:>4}%", fg=bb_color)
        else:
            bb_str = typer.style("  — ", fg=typer.colors.BRIGHT_BLACK)

        # Color score
        if c.score >= 70:
            score_color = typer.colors.GREEN
        elif c.score >= 40:
            score_color = typer.colors.YELLOW
        else:
            score_color = typer.colors.WHITE

        line = (
            f"{i:>3} {c.ticker:<7} "
            + typer.style(f"{c.score:>6.1f}", fg=score_color)
            + f" {streak_str:>7} {net_days_str:>9} {_format_value(c.total_net_value):>12}"
            + f" {flow_str:>6} {vwap_str:>10} {rsi_str:>6} {bb_str}  {c.trend:>5}"
        )
        typer.echo(line)

        if show_breakdown and c.score_breakdown:
            bd = c.score_breakdown
            typer.echo(
                f"    [cons={bd.get('cons', 0):.1f} streak={bd.get('streak', 0):.1f}"
                f" vwap={bd.get('vwap', 0):.1f} rsi={bd.get('rsi', 0):.1f}"
                f" flow={bd.get('flow', 0):.1f} bb={bd.get('bb', 0):.1f}"
                f" inst={bd.get('inst', 0):.1f}]"
            )

        if granular and c.top_brokers:
            broker_line = "    " + "  ".join(c.top_brokers[:5])
            if c.institutional_flag:
                broker_line += "  " + typer.style("[★ INSTITUTIONAL]", fg=typer.colors.CYAN)
            typer.echo(broker_line)

    typer.echo("-" * _SEP_WIDTH)
    typer.echo(
        f"Checked: {response.total_tickers_checked} | "
        f"Shown: {len(candidates)} | "
        f"Skipped (no data): {response.tickers_skipped}"
    )
    typer.echo(f"Provider: {response.provider} (aggregate foreign flow)")
    if response.provider == "idx":
        typer.echo(
            "  For per-broker detail: set Stockbit token via `saham broker auth <token>`"
        )
    typer.echo("")
    typer.echo("FLOW%: avg net foreign % of total daily turnover (positive = accumulating)")
    typer.echo("VWAP_DISC: positive = price < foreign avg buy (foreigners underwater)")
    typer.echo("BB%ILE: BB Width pctile vs last 60d — green(≤20%) = squeeze (coiled spring)")
    typer.echo("Score 0–120 | consistency 40 | streak 30 | VWAP 20 | RSI 10 | flow 10 | BB 10 | inst 5")
    typer.echo("")
    typer.echo("Swing trade watchlist — cross-check with `saham screen pre-open` for intraday entry timing.")
    typer.echo("DISCLAIMER: Analysis only, not trading advice.")
    typer.echo("=" * _TABLE_WIDTH)


def _run_multi(
    use_case: AccumulationScreenUseCase,
    tickers: list[str],
    windows: list[int],
    base_request: AccumulationScreenRequest,
) -> dict[int, AccumulationScreenResponse]:
    """Run screener for each window. Always min_score=0 to get full picture."""
    return {
        w: use_case.execute(AccumulationScreenRequest(
            tickers=tickers,
            window_days=w,
            min_net_buy_days=base_request.min_net_buy_days,
            min_score=0.0,
            rsi_period=base_request.rsi_period,
            sma_period=base_request.sma_period,
        ))
        for w in windows
    }


def _display_multi(
    results: dict[int, AccumulationScreenResponse],
    universe_label: str,
    top_n: int,
    sort_by: str,
    squeeze_only: bool,
    screened_at: "date",
) -> None:
    """Render multi-window side-by-side table."""
    windows = sorted(results.keys())

    # Build per-ticker dict: ticker -> {window -> candidate}
    by_ticker: dict[str, dict[int, AccumulationCandidate]] = {}
    for w, resp in results.items():
        for c in resp.candidates:
            by_ticker.setdefault(c.ticker, {})[w] = c

    # Apply squeeze filter
    if squeeze_only:
        by_ticker = {
            tk: pw for tk, pw in by_ticker.items()
            if any(
                c.bb_width_pctile is not None and c.bb_width_pctile <= 0.20
                for c in pw.values()
            )
        }

    def sort_key(item: tuple) -> float:
        pw = item[1]
        scores = [c.score for c in pw.values()]
        if not scores:
            return 0.0
        if sort_by == "avg":
            return sum(scores) / len(scores)
        if sort_by == "max":
            return max(scores)
        try:
            w = int(sort_by.rstrip("d"))
            c = pw.get(w)
            return c.score if c else 0.0
        except (ValueError, AttributeError):
            return sum(scores) / len(scores)

    rows = sorted(by_ticker.items(), key=sort_key, reverse=True)[:top_n]

    typer.echo("")
    typer.echo("=" * _TABLE_WIDTH)
    typer.echo(
        f"FOREIGN ACCUMULATION — {universe_label.upper()} "
        f"| MULTI-WINDOW | {screened_at}"
    )
    typer.echo("=" * _TABLE_WIDTH)

    if not rows:
        typer.echo("No candidates found matching the criteria.")
        typer.echo("=" * _TABLE_WIDTH)
        return

    win_headers = "  ".join(f"{w:>4}d" for w in windows)
    typer.echo(f"{'#':>3} {'TICKER':<7} {win_headers}  {'PATTERN':<18} {'TREND':>5}")
    typer.echo("-" * _SEP_WIDTH)

    for i, (tk, pw) in enumerate(rows, 1):
        cells = "  ".join(_fmt_score(pw.get(w).score if pw.get(w) else None) for w in windows)
        pattern = _classify_pattern(windows, pw)
        trend = next((c.trend for w in sorted(windows) for c in [pw.get(w)] if c), "—")
        typer.echo(f"{i:>3} {tk:<7} {cells}  {pattern:<18} {trend:>5}")

    sample_resp = next(iter(results.values()))
    typer.echo("-" * _SEP_WIDTH)
    typer.echo(
        f"Checked: {sample_resp.total_tickers_checked} | "
        f"Shown: {len(rows)} | "
        f"Provider: {sample_resp.provider}"
    )
    typer.echo("Score ≥70 green | ≥40 yellow | <40 white")
    typer.echo("Patterns: sustained | building | fresh rotation | long-term only | coiled spring | weak")
    typer.echo("DISCLAIMER: Analysis only, not trading advice.")
    typer.echo("=" * _TABLE_WIDTH)


def _print_column_guide() -> None:
    """Print a terminal-friendly reference guide for every column and signal."""

    def _h(text: str) -> None:
        typer.echo("")
        typer.echo(typer.style(f"  {text}", fg=typer.colors.CYAN, bold=True))
        typer.echo(typer.style("  " + "─" * (len(text) + 2), fg=typer.colors.BRIGHT_BLACK))

    def _row(label: str, value: str) -> None:
        typer.echo(f"    {typer.style(label, fg=typer.colors.YELLOW):<30} {value}")

    typer.echo("")
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo(typer.style("  FOREIGN ACCUMULATION SCREENER — COLUMN GUIDE", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo("")
    typer.echo("  Detects stocks being quietly bought by foreign institutions over")
    typer.echo("  multiple days. When foreigners accumulate consistently AND are")
    typer.echo("  'underwater' (bought higher than today's price), IHSG stocks")
    typer.echo("  resolve upward 65–70% of the time within 10–20 trading days.")
    typer.echo("  This is a swing trade watchlist (5–20 day horizon).")

    # ── SCORE ──
    _h("SCORE  (0–120)")
    typer.echo("  Composite signal strength. Combines all signals below into one number.")
    typer.echo("  Higher = more confident that accumulation is real and setup is clean.")
    _row("≥ 70 (green)", "Strong signal — worth researching")
    _row("40–69 (yellow)", "Moderate — watch, wait for confirmation")
    _row("< 40 (white)", "Weak — likely noise, skip")
    typer.echo("")
    typer.echo("  Use --breakdown to see exactly how each component contributed.")

    # ── STREAK ──
    _h("STREAK  — Consecutive Buy Days")
    typer.echo("  How many trading days IN A ROW foreigners ended up as net buyers,")
    typer.echo("  counting backwards from today. A streak means systematic intent.")
    _row("1–2d", "Inconclusive")
    _row("3–4d", "Noteworthy — watch this ticker")
    _row("5–7d", "Strong — likely intentional accumulation")
    _row("8d+", "Very strong — institution is committed")
    typer.echo("")
    typer.echo("  Scoring: exponential curve (τ=7d). 7d streak ≈ 63% of max,")
    typer.echo("  14d ≈ 86%. Longer streaks always score higher — no hard cap.")

    # ── NET_DAYS ──
    _h("NET_DAYS  — Consistency Ratio  (e.g. 5/7)")
    typer.echo("  Net buy days / total days in window. 5/7 = foreigners bought on 5")
    typer.echo("  of the last 7 trading days. This is the highest-weight signal (40 pts).")
    _row("100% (4/4, 7/7)", "Every day was a buy — strong conviction")
    _row("70–99%", "Most days positive — healthy trend")
    _row("50–69%", "Mixed — watch for deterioration")
    _row("< 50%", "More sell days than buy — not accumulation")
    typer.echo("")
    typer.echo("  A stock with 4/4 is stronger than 10/30 even if the streak looks similar.")

    # ── NET_VALUE ──
    _h("NET_VALUE  — Total Net Foreign Flow (IDR)")
    typer.echo("  Total (foreign buys − foreign sells) over the window in IDR.")
    typer.echo("  Confirms real money is behind the consistency signal.")
    _row("+19.4B", "Net bought Rp 19.4 billion — meaningful size")
    _row("+10M", "Net bought Rp 10 million — may be too small")
    typer.echo("")
    typer.echo("  T = trillion  |  B = billion  |  M = million  (IDR)")

    # ── FLOW% ──
    _h("FLOW%  — Foreign Dominance of Daily Volume")
    typer.echo("  Average % of total daily turnover that was net foreign buying.")
    typer.echo("  Unlike NET_VALUE (absolute IDR), this is relative — a mid-cap")
    typer.echo("  at 35% FLOW% is a stronger signal than a large-cap at 3%.")
    _row("0–5%", "Minor participation")
    _row("5–15%", "Meaningful foreign interest")
    _row("15–30%", "Foreigners are a major force in this stock")
    _row("30%+", "Foreigners dominating — very strong signal")
    typer.echo("")
    typer.echo("  Scoring: contributes up to 10 pts, saturates at 20% flow ratio.")

    # ── VWAP_DISC ──
    _h("VWAP_DISC  — Foreigners' Profit / Loss on Position")
    typer.echo("  Compares foreigners' average buy price (VWAP) to today's price.")
    typer.echo("")
    typer.echo("  POSITIVE (+8.4%) = foreigners bought HIGHER than today's price.")
    typer.echo("  They are underwater (in a paper loss) and motivated to defend.")
    typer.echo("  When they keep buying despite a loss, they expect a recovery.")
    typer.echo("  This creates a price floor — they absorb selling to protect position.")
    typer.echo("")
    typer.echo("  NEGATIVE (−1.9%) = foreigners are in profit. Less urgency to defend.")
    _row("  > +5%", "Meaningfully underwater — strong defense motive")
    _row("  +1% to +5%", "Slightly underwater — moderate signal")
    _row("  < 0%", "In profit — less motivated to defend")
    _row("  — (dash)", "Insufficient buy data to compute VWAP")
    typer.echo("")
    typer.echo("  Scoring: linear ramp. 10% underwater = full 20 pts. 5% = 10 pts.")

    # ── RSI ──
    _h("RSI  — Room Left to Run  (14-day)")
    typer.echo("  Relative Strength Index — measures price momentum (0–100).")
    typer.echo("  For accumulation, you want to enter BEFORE a move, not after.")
    _row("  > 70", "Overbought — most of the move already happened")
    _row("  55–70", "Building momentum — getting stretched")
    _row("  40–55", "Healthy — moving but not overextended")
    _row("  25–40", "Weak/recovering — ideal entry zone")
    _row("  < 25", "Severe panic — high risk, possible capitulation")
    typer.echo("")
    typer.echo("  Scoring: tent peak at RSI=40 (10 pts). Zero at RSI≤25 or ≥75.")
    typer.echo("  RSI 40 with a 5-day streak = smart money re-entering during weakness.")

    # ── BB%ILE ──
    _h("BB%ILE  — Bollinger Band Squeeze  (green ≤ 20%)")
    typer.echo("  Percentile rank of today's Bollinger Band width vs last 60 days.")
    typer.echo("  BB Width measures price channel size — narrow = compressed volatility.")
    typer.echo("")
    typer.echo("  LOW BB%ILE = the band is TIGHTER than usual = SQUEEZE.")
    typer.echo("  When a stock trades flat (low vol) while foreigners accumulate,")
    typer.echo("  it is a 'coiled spring'. Compression releases suddenly on a catalyst.")
    _row("  ≤ 20% (green)", "Squeeze — coiled spring, watch closely")
    _row("  21–40% (yellow)", "Moderately tight — building")
    _row("  > 40%", "Normal or expanding volatility")
    _row("  — (dash)", "< 60 days of price data in local DB")
    typer.echo("")
    typer.echo("  Scoring: bottom 20th pctile earns 5–10 pts; 40th pctile earns 0–5 pts.")
    typer.echo("  Use --squeeze-only to filter exclusively for these setups.")

    # ── TREND ──
    _h("TREND  — Price vs SMA20")
    typer.echo("  Whether the stock is above or below its 20-day moving average.")
    _row("  UP", "> 2% above SMA20 — uptrend")
    _row("  DOWN", "> 2% below SMA20 — downtrend")
    _row("  SIDE", "Within ±2% of SMA20 — ranging")
    typer.echo("")
    typer.echo("  For accumulation setups, DOWN or SIDE is often ideal — you want to")
    typer.echo("  enter BEFORE the trend turns UP, not after the move has started.")

    # ── PATTERN (multi-window) ──
    _h("PATTERN  — Multi-Window Summary  (--multi only)")
    typer.echo("  Labels what the 7d/30d/90d score comparison reveals.")
    _row("  sustained", "Score ≥60 on all 3 windows — months of buildup, highest conviction")
    _row("  building", "Strong 7d+30d, weaker 90d — accumulation intensifying recently")
    _row("  fresh rotation", "Strong 7d only — very recent, needs time to confirm")
    _row("  long-term only", "Strong 90d, weak recent — may be complete, watch for exit")
    _row("  coiled spring", "Squeeze + score ≥60 on any window — compressed, ready to break")
    _row("  weak", "No window scores ≥60 — not a meaningful setup")

    # ── BREAKDOWN ──
    _h("SCORE BREAKDOWN  (--breakdown flag)")
    typer.echo("  Shows exactly how each component contributed to the total score.")
    typer.echo("  Format: [cons=X streak=X vwap=X rsi=X flow=X bb=X inst=X]")
    _row("  cons", "Up to 40 pts — net buy day consistency")
    _row("  streak", "Up to 30 pts — consecutive buy days (exponential)")
    _row("  vwap", "Up to 20 pts — how underwater foreigners are")
    _row("  rsi", "Up to 10 pts — RSI headroom (tent at 40)")
    _row("  flow", "Up to 10 pts — avg % of daily turnover that's foreign")
    _row("  bb", "Up to 10 pts — BB Width squeeze intensity")
    _row("  inst", "Up to  5 pts — institutional broker detected (Stockbit only)")
    typer.echo("")
    typer.echo("  If a stock scores lower than expected, breakdown shows which signal")
    typer.echo("  is missing. E.g. vwap=0 means foreigners are in profit — no defense motive.")

    # ── IDEAL SETUP ──
    _h("IDEAL CANDIDATE CHECKLIST")
    typer.echo("  In priority order:")
    typer.echo("    1. PATTERN = sustained or coiled spring  (multi-window confirms)")
    typer.echo("    2. STREAK ≥ 5d                          (systematic, not opportunistic)")
    typer.echo("    3. VWAP_DISC > 0%                       (foreigners defending position)")
    typer.echo("    4. BB%ILE ≤ 20% (green)                 (compressed, spring loaded)")
    typer.echo("    5. RSI between 30–50                    (room to run)")
    typer.echo("    6. FLOW% > 15%                          (foreigners dominating volume)")
    typer.echo("    7. NET_DAYS ≥ 70%                       (consistent, not just a streak)")
    typer.echo("")
    typer.echo("  No single signal is definitive. A stock meeting 5 of 7 criteria is")
    typer.echo("  a much stronger candidate than one barely crossing a score threshold.")

    # ── TIPS ──
    _h("QUICK TIPS")
    typer.echo("  Run --multi first for the daily overview — one command, three windows.")
    typer.echo("  Use --squeeze-only to surface 'coiled spring' setups.")
    typer.echo("  Deep-dive: saham broker flow <TICKER> --days 30")
    typer.echo("             saham risk <TICKER> --profile balanced --with-sentiment")
    typer.echo("")
    typer.echo(typer.style("  DISCLAIMER: Analysis only. Not financial advice.", fg=typer.colors.BRIGHT_BLACK))
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo("")


@accumulation_app.command("run")
def accumulation_run(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe", "-u",
            help="Universe: lq45, idx80, idxcomp100, cached",
        ),
    ] = None,
    window: Annotated[
        int,
        typer.Option(
            "--window", "-w",
            help="Analysis window in days (7, 30, or 90)",
            min=3,
        ),
    ] = 7,
    min_streak: Annotated[
        int,
        typer.Option("--min-streak", help="Minimum consecutive buy days required", min=0),
    ] = 0,
    min_score: Annotated[
        float,
        typer.Option("--min-score", help="Minimum composite score (0–120)", min=0),
    ] = 0.0,
    vwap_only: Annotated[
        bool,
        typer.Option("--vwap-only", help="Only show stocks where foreigners are underwater"),
    ] = False,
    squeeze_only: Annotated[
        bool,
        typer.Option("--squeeze-only", help="Only show stocks in BB squeeze (BB width pctile ≤ 20%)"),
    ] = False,
    top: Annotated[
        int,
        typer.Option("--top", help="Show top N results", min=1),
    ] = 20,
    granular: Annotated[
        bool,
        typer.Option("--granular", help="Show per-broker detail (Stockbit data required)"),
    ] = False,
    show_breakdown: Annotated[
        bool,
        typer.Option("--breakdown", help="Show per-component score breakdown under each row"),
    ] = False,
    multi: Annotated[
        bool,
        typer.Option("--multi", help="Show scores across multiple windows side-by-side"),
    ] = False,
    windows: Annotated[
        Optional[str],
        typer.Option("--windows", help="Comma-separated window days for --multi (default: 7,30,90)"),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option("--sort-by", help="In --multi mode, sort by: avg|max|7d|30d|90d (default: avg)"),
    ] = "avg",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    guide: Annotated[
        bool,
        typer.Option("--guide", help="Print column reference guide and exit (no screen needed)"),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Print column guide appended after results"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Screen stocks for foreign accumulation patterns.

    Scores each ticker 0–120 based on: consistency of daily foreign buying,
    consecutive buy streak, whether foreigners are underwater (VWAP vs price),
    RSI headroom, foreign flow as % of total turnover, and BB Width squeeze.

    Run `saham update --universe lq45` first to ensure fresh data.

    Examples:
        saham screen accumulation --universe lq45
        saham screen accumulation --universe lq45 --window 30
        saham screen accumulation --universe lq45 --multi
        saham screen accumulation --universe lq45 --multi --sort-by 30d
        saham screen accumulation --universe lq45 --min-score 50 --top 10
        saham screen accumulation BBCA BBRI BMRI --window 7
        saham screen accumulation --universe lq45 --vwap-only
        saham screen accumulation --universe lq45 --squeeze-only
        saham screen accumulation --universe lq45 --granular
        saham screen accumulation --universe lq45 --breakdown
        saham screen accumulation --universe lq45 --explain
        saham screen accumulation --guide
        saham screen accumulation --universe lq45 --format json
    """
    if guide:
        _print_column_guide()
        return

    resolved_db = db_path or DEFAULT_DB_PATH

    # Resolve tickers
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to screen. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    universe_label = universe or f"{len(ticker_list)} tickers"

    broker_repo = SQLiteBrokerRepository(resolved_db)
    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    use_case = AccumulationScreenUseCase(
        broker_repository=broker_repo,
        market_repository=market_repo,
    )

    base_request = AccumulationScreenRequest(
        tickers=ticker_list,
        window_days=window,
        min_net_buy_days=max(1, min_streak),
        min_score=min_score,
    )

    # --- Multi-window mode ---
    if multi:
        window_list = [int(w.strip()) for w in (windows or "7,30,90").split(",")]
        typer.echo(
            f"Screening {len(ticker_list)} tickers | windows: {', '.join(str(w)+'d' for w in window_list)}..."
        )
        multi_results = _run_multi(use_case, ticker_list, window_list, base_request)
        screened_at = next(iter(multi_results.values())).screened_at

        if output_format == "json":
            by_ticker: dict = {}
            for w, resp in multi_results.items():
                for c in resp.candidates:
                    by_ticker.setdefault(c.ticker, {})[f"{w}d"] = c.to_dict()
            typer.echo(json.dumps({
                "mode": "multi",
                "windows": [f"{w}d" for w in sorted(multi_results.keys())],
                "screened_at": str(screened_at),
                "tickers": by_ticker,
            }, indent=2, default=str))
            return

        _display_multi(
            results=multi_results,
            universe_label=universe_label,
            top_n=top,
            sort_by=sort_by,
            squeeze_only=squeeze_only,
            screened_at=screened_at,
        )
        if explain:
            _print_column_guide()
        return

    # --- Single-window mode ---
    typer.echo(
        f"Screening {len(ticker_list)} tickers | {window}d window..."
    )
    response = use_case.execute(base_request)

    # Apply streak filter post-scoring
    if min_streak > 0:
        response.candidates = [
            c for c in response.candidates if c.consecutive_streak >= min_streak
        ]

    if output_format == "json":
        data = {
            "screened_at": str(response.screened_at),
            "window_days": response.window_days,
            "total_checked": response.total_tickers_checked,
            "skipped": response.tickers_skipped,
            "provider": response.provider,
            "candidates": [c.to_dict() for c in response.candidates[:top]],
        }
        typer.echo(json.dumps(data, indent=2, default=str))
        return

    _display_results(
        response=response,
        universe_label=universe_label,
        top_n=top,
        granular=granular,
        vwap_only=vwap_only,
        squeeze_only=squeeze_only,
        show_breakdown=show_breakdown,
    )
    if explain:
        _print_column_guide()


# ---------------------------------------------------------------------------
# Universe management commands
# ---------------------------------------------------------------------------

@universe_app.command("list")
def universe_list(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to universes.yaml"),
    ] = None,
) -> None:
    """
    List configured ticker universes with last-updated date and ticker count.

    Example:
        saham universe list
    """
    from src.application.services.universe_loader import UNIVERSE_CONFIG_PATH

    resolved_config = config_path or UNIVERSE_CONFIG_PATH
    meta = load_universe_meta(resolved_config)

    if not meta:
        typer.echo(f"No universe config found at '{resolved_config}'.")
        typer.echo("Expected: config/universes.yaml")
        raise typer.Exit(1)

    typer.echo("")
    typer.echo("Configured universes:")
    typer.echo(f"  {'NAME':<14} {'TICKERS':>8}  {'LAST UPDATED'}")
    typer.echo("  " + "-" * 40)
    for name, info in meta.items():
        typer.echo(f"  {name:<14} {info['count']:>8}  {info['updated']}")
    typer.echo("")
    typer.echo(f"Config file: {resolved_config}")
    typer.echo("")
    typer.echo("Usage: saham update --universe <name>")
    typer.echo("       saham screen accumulation --universe <name>")


@universe_app.command("update")
def universe_update(
    universe_name: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe to update (lq45, idx80, idxcomp100)"),
    ] = None,
) -> None:
    """
    Refresh universe ticker lists from IDX website.

    Currently prints instructions — automatic scraping from IDX
    will be implemented in a future release.

    Example:
        saham universe update --universe lq45
    """
    typer.echo("")
    typer.echo("Universe auto-update from IDX website is not yet implemented.")
    typer.echo("")
    typer.echo("To update manually:")
    typer.echo("  1. Visit https://www.idx.co.id/en/market-data/indexes/")
    typer.echo("  2. Download the latest LQ45 / IDX80 constituent list")
    typer.echo("  3. Edit config/universes.yaml with the new tickers")
    typer.echo("  4. Update the 'updated' date field")
    typer.echo("")
    typer.echo("IDX rebalances indices every February and August.")
