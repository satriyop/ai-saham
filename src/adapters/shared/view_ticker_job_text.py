"""Pure multi-surface text formatters for stock-axis ticker jobs.

Jobs: flow · foreign-history · distribution · financials
(CLI: view ticker flow|foreign-history|distribution|financials)

Layer: Adapter (shared pure presentation — no IO)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.adapters.shared.view_number_format import format_value


@dataclass(frozen=True)
class TickerJobText:
    """Browse-only ticker job body for CLI parity text / TUI paint."""

    job: str  # flow | foreign | dist | fin
    ticker: str
    title: str
    body: str
    empty: bool
    fetch_hint: str
    cli_verb: str
    # Optional structured desk model for TUI (flow first; other jobs later)
    desk: Any = None

    def as_text(self) -> str:
        return f"{self.title}\n\n{self.body}".strip()


def _fmt_signed(value: Decimal | float | int) -> str:
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    s = format_value(d)
    if d > 0 and not s.startswith("+"):
        return f"+{s}"
    return s


def format_ticker_flow_job(
    ticker: str,
    summaries: Sequence[Any],
    *,
    total_net: Decimal | None = None,
    buy_days: int | None = None,
    sell_days: int | None = None,
    window_days: int | None = None,
    source: str | None = None,
    as_of: Any = None,
    fetch_hint: str | None = None,
) -> TickerJobText:
    """Format ViewTickerFlowResult summaries (foreign flow / broker_summaries).

    Body text stays multi-surface; ``desk`` carries structured flow job UI.
    """
    from src.adapters.shared.ticker_flow_desk_model import build_ticker_flow_desk_model

    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch market {ticker_u}"
    desk = build_ticker_flow_desk_model(
        ticker_u,
        summaries,
        total_net=total_net,
        buy_days=buy_days,
        sell_days=sell_days,
        window_days=(
            window_days if window_days is not None else (len(list(summaries or ())) or None)
        ),
        source=source,
        as_of=as_of,
        fetch_hint=hint,
    )
    if desk.empty:
        return TickerJobText(
            job="flow",
            ticker=ticker_u,
            title=desk.title,
            body=f"not cached · foreign flow summary empty\nHint: {hint}",
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker flow",
            desk=desk,
        )

    # CLI-parity body (same facts as desk; table newest-first for scan)
    lines: list[str] = [
        f"Foreign flow · {ticker_u} · last {len(desk.days)} sessions",
        f"Total net  {desk.hero_big}  ·  "
        f"buy/sell days {desk.pulses[0].value}/{desk.pulses[1].value}  ·  "
        f"consec buy {desk.pulses[2].value}",
        "",
        f"{'Date':12}  {'Net':>12}  {'Ratio':>8}  {'Buyer':>6}  {'Seller':>6}",
        "─" * 52,
    ]
    for d in desk.days:
        lines.append(f"{d.date_s:12}  {d.net_s:>12}  {d.ratio_s:>8}  {d.buyer:>6}  {d.seller:>6}")
    lines.append("")
    lines.append("CLI · saham view ticker flow  ·  local cache · browse only")
    return TickerJobText(
        job="flow",
        ticker=ticker_u,
        title=desk.title,
        body="\n".join(lines),
        empty=False,
        fetch_hint=hint,
        cli_verb="view ticker flow",
        desk=desk,
    )


def format_ticker_foreign_history_job(
    ticker: str,
    points: Sequence[Any],
    *,
    resolved_source: str = "—",
    window_days: int | None = None,
    as_of: Any = None,
    fetch_hint: str | None = None,
) -> TickerJobText:
    """Format foreign_flow_points series (foreign-history).

    Body text stays multi-surface; ``desk`` carries structured foreign job UI.
    """
    from src.adapters.shared.ticker_foreign_desk_model import (
        build_ticker_foreign_desk_model,
    )

    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch broker-history {ticker_u}"
    desk = build_ticker_foreign_desk_model(
        ticker_u,
        points,
        resolved_source=resolved_source,
        window_days=window_days if window_days is not None else len(list(points or ())),
        as_of=as_of,
        fetch_hint=hint,
    )
    if desk.empty:
        return TickerJobText(
            job="foreign",
            ticker=ticker_u,
            title=desk.title,
            body=f"not cached · foreign flow points empty\nHint: {hint}",
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker foreign-history",
            desk=desk,
        )

    lines: list[str] = [
        f"Foreign history · {ticker_u} · source {desk.source} · last {len(desk.days)} days",
        f"Latest  {desk.hero_big}  ·  5d {desk.pulses[0].value}  ·  20d {desk.pulses[1].value}",
        "",
        f"{'Date':12}  {'Source':10}  {'Net':>12}  {'Lot':>10}  {'Avg':>10}",
        "─" * 58,
    ]
    for d in desk.days:
        lines.append(f"{d.date_s:12}  {d.source:10}  {d.net_s:>12}  {d.lot_s:>10}  {d.avg_s:>10}")
    lines.append("")
    lines.append("CLI · saham view ticker foreign-history  ·  local cache · browse only")
    return TickerJobText(
        job="foreign",
        ticker=ticker_u,
        title=desk.title,
        body="\n".join(lines),
        empty=False,
        fetch_hint=hint,
        cli_verb="view ticker foreign-history",
        desk=desk,
    )


def _broker_tag(code: str, btype: str) -> str:
    """Type tags: F = Foreign (incl. asing), L = Local, G = government if ever present."""
    t = (btype or "").lower()
    if t in {"asing", "foreign", "f"}:
        tag = "F"
    elif t in {"pemerintah", "government", "g"}:
        tag = "G"
    else:
        tag = "L"
    return f"{code}[{tag}]"


def _fmt_idr_amount(amount: int) -> str:
    abs_amt = abs(amount)
    if abs_amt >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.1f}T"
    if abs_amt >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}B"
    if abs_amt >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    return f"{amount:,}"


def format_ticker_distribution_job(
    ticker: str,
    snapshot: Any | None,
    *,
    as_of: Any = None,
    source: str | None = None,
    fetch_hint: str | None = None,
) -> TickerJobText:
    """Format BrokerDistributionSnapshot (cross-broker counterparties).

    Body text stays multi-surface; ``desk`` carries structured dist job UI.
    """
    from src.adapters.shared.ticker_dist_desk_model import build_ticker_dist_desk_model

    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch market {ticker_u}"
    desk = build_ticker_dist_desk_model(
        ticker_u,
        snapshot,
        as_of=as_of,
        source=source,
        fetch_hint=hint,
    )
    if desk.empty and snapshot is None:
        return TickerJobText(
            job="dist",
            ticker=ticker_u,
            title=desk.title,
            body=f"not cached · broker distribution empty\nHint: {hint}",
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker distribution",
            desk=desk,
        )

    # CLI-parity body from same desk facts (F/L tags, never A)
    lines: list[str] = [
        f"Broker distribution · {ticker_u} · {desk.as_of}",
    ]
    if desk.slogan:
        lines.append(desk.slogan)
    lines.append("")
    if desk.buyers:
        lines.append("TOP BUYERS  (bought FROM →)")
        lines.append("─" * 48)
        for s in desk.buyers:
            lines.append(f"  {s.code}[{s.type_tag}]  {s.amount_s:>10}")
            for cp in s.cps:
                lines.append(f"    ← {cp.code}[{cp.type_tag}]  {cp.amount_s:>10}  ({cp.pct}%)")
        lines.append("")
    if desk.sellers:
        lines.append("TOP SELLERS (sold TO →)")
        lines.append("─" * 48)
        for s in desk.sellers:
            lines.append(f"  {s.code}[{s.type_tag}]  {s.amount_s:>10}")
            for cp in s.cps:
                lines.append(f"    → {cp.code}[{cp.type_tag}]  {cp.amount_s:>10}  ({cp.pct}%)")
        lines.append("")
    if desk.empty:
        lines.append(f"Hint: {hint}")
    lines.append("CLI · saham view ticker distribution  ·  local cache · browse only")
    return TickerJobText(
        job="dist",
        ticker=ticker_u,
        title=desk.title,
        body="\n".join(lines),
        empty=desk.empty,
        fetch_hint=hint,
        cli_verb="view ticker distribution",
        desk=desk,
    )


def _fmt_fin_idr(value: float | int | None) -> str:
    if value is None:
        return "—"
    v = float(value)
    if abs(v) >= 1e12:
        return f"{v / 1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"{v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f}M"
    return f"{v:,.0f}"


def _fmt_eps(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}"


def format_ticker_financials_job(
    ticker: str,
    results: Sequence[Any],
    *,
    fetch_hint: str | None = None,
) -> TickerJobText:
    """Format one or more ViewTickerFinancialsResult (income/balance/cashflow)."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch financials {ticker_u}"
    if not results:
        return TickerJobText(
            job="fin",
            ticker=ticker_u,
            title=f"View · ticker · {ticker_u} · financials",
            body=f"not cached · no financial statements\nHint: {hint}",
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker financials",
        )

    lines: list[str] = [f"Financials · {ticker_u} · local cache", ""]
    any_ok = False
    for result in results:
        statement = str(getattr(result, "statement", "income") or "income")
        period_type = str(getattr(result, "period_type", "quarter") or "quarter")
        status = str(getattr(result, "status", "empty") or "empty")
        periods = list(getattr(result, "periods", ()) or ())
        lines.append(f"── {statement.title()} · {period_type} ──")
        if status != "ok" or not periods:
            msg = getattr(result, "message", None) or "No periods cached"
            lines.append(f"  {msg}")
            lines.append("")
            continue
        any_ok = True
        src = getattr(result, "source", None) or "—"
        lines.append(f"  source={src} · {len(periods)} periods")
        # Compact rows: period + key metrics by kind
        for p in periods[:8]:
            pe = getattr(p, "period_end", None)
            pe_s = pe.isoformat() if pe is not None and hasattr(pe, "isoformat") else str(pe or "—")
            if statement == "income":
                lines.append(
                    f"  {pe_s}  rev {_fmt_fin_idr(getattr(p, 'total_revenue', None))}  "
                    f"ni {_fmt_fin_idr(getattr(p, 'net_income', None))}  "
                    f"eps {_fmt_eps(getattr(p, 'eps_basic', None))}"
                )
            elif statement == "balance":
                lines.append(
                    f"  {pe_s}  assets {_fmt_fin_idr(getattr(p, 'total_assets', None))}  "
                    f"equity {_fmt_fin_idr(getattr(p, 'stockholders_equity', None))}  "
                    f"debt {_fmt_fin_idr(getattr(p, 'total_debt', None))}"
                )
            else:
                lines.append(
                    f"  {pe_s}  op {_fmt_fin_idr(getattr(p, 'operating_cash_flow', None))}  "
                    f"fcf {_fmt_fin_idr(getattr(p, 'free_cash_flow', None))}  "
                    f"capex {_fmt_fin_idr(getattr(p, 'capital_expenditure', None))}"
                )
        lines.append("")

    if not any_ok:
        lines.append(f"Hint: {hint}")
    lines.append("CLI · saham view ticker financials  ·  local cache · browse only")
    return TickerJobText(
        job="fin",
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · financials",
        body="\n".join(lines),
        empty=not any_ok,
        fetch_hint=hint,
        cli_verb="view ticker financials",
    )


def empty_ticker_job(job: str, ticker: str, *, message: str = "not cached") -> TickerJobText:
    """Honest empty job body when use case returns None."""
    ticker_u = str(ticker).upper()
    verbs = {
        "flow": ("view ticker flow", f"saham fetch market {ticker_u}"),
        "foreign": ("view ticker foreign-history", f"saham fetch broker-history {ticker_u}"),
        "dist": ("view ticker distribution", f"saham fetch market {ticker_u}"),
        "fin": ("view ticker financials", f"saham fetch financials {ticker_u}"),
    }
    cli, hint = verbs.get(job, (f"view ticker {job}", f"saham fetch market {ticker_u}"))
    titles = {
        "flow": "flow",
        "foreign": "foreign-history",
        "dist": "distribution",
        "fin": "financials",
    }
    label = titles.get(job, job)
    return TickerJobText(
        job=job,
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · {label}",
        body=f"{message}\nHint: {hint}\nCLI · saham {cli} {ticker_u}",
        empty=True,
        fetch_hint=hint,
        cli_verb=cli,
    )
