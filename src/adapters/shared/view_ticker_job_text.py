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
    fetch_hint: str | None = None,
) -> TickerJobText:
    """Format ViewTickerFlowResult summaries (foreign flow / broker_summaries)."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch market {ticker_u}"
    if not summaries:
        return TickerJobText(
            job="flow",
            ticker=ticker_u,
            title=f"View · ticker · {ticker_u} · flow",
            body=f"not cached · foreign flow summary empty\nHint: {hint}",
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker flow",
        )

    rows = list(summaries)
    total = total_net
    if total is None:
        total = sum((getattr(s, "foreign_net_value", Decimal("0")) for s in rows), Decimal("0"))
    buys = buy_days
    if buys is None:
        buys = sum(1 for s in rows if getattr(s, "is_foreign_accumulating", False))
    sells = sell_days if sell_days is not None else len(rows) - int(buys)

    consecutive = 0
    for s in reversed(rows):
        if getattr(s, "is_foreign_accumulating", False):
            consecutive += 1
        else:
            break

    lines: list[str] = [
        f"Foreign flow · {ticker_u} · last {len(rows)} sessions",
        f"Total net  {_fmt_signed(total)}  ·  buy/sell days {buys}/{sells}  ·  "
        f"consec buy {consecutive}",
        "",
        f"{'Date':12}  {'Net':>12}  {'Ratio':>8}  {'Buyer':>6}  {'Seller':>6}",
        "─" * 52,
    ]
    for s in rows:
        flow = getattr(s, "foreign_net_value", Decimal("0"))
        ratio = getattr(s, "foreign_flow_ratio", Decimal("0"))
        try:
            ratio_f = float(ratio)
        except (TypeError, ValueError):
            ratio_f = 0.0
        buyers = getattr(s, "top_buyers", ()) or ()
        sellers = getattr(s, "top_sellers", ()) or ()
        top_b = getattr(buyers[0], "broker_code", "-") if buyers else "-"
        top_s = getattr(sellers[0], "broker_code", "-") if sellers else "-"
        d = getattr(s, "date", None)
        d_s = d.isoformat() if d is not None and hasattr(d, "isoformat") else str(d or "—")
        lines.append(
            f"{d_s:12}  {_fmt_signed(flow):>12}  {ratio_f:7.1f}%  {str(top_b):>6}  {str(top_s):>6}"
        )
    lines.append("")
    lines.append("CLI · saham view ticker flow  ·  local cache · browse only")
    return TickerJobText(
        job="flow",
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · flow",
        body="\n".join(lines),
        empty=False,
        fetch_hint=hint,
        cli_verb="view ticker flow",
    )


def format_ticker_foreign_history_job(
    ticker: str,
    points: Sequence[Any],
    *,
    resolved_source: str = "—",
    fetch_hint: str | None = None,
) -> TickerJobText:
    """Format foreign_flow_points series (foreign-history)."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch broker-history {ticker_u}"
    if not points:
        return TickerJobText(
            job="foreign",
            ticker=ticker_u,
            title=f"View · ticker · {ticker_u} · foreign-history",
            body=f"not cached · foreign flow points empty\nHint: {hint}",
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker foreign-history",
        )

    lines: list[str] = [
        f"Foreign history · {ticker_u} · source {resolved_source} · last {len(points)} days",
        "",
        f"{'Date':12}  {'Source':10}  {'Net':>12}  {'Lot':>10}  {'Avg':>10}",
        "─" * 58,
    ]
    for p in points:
        d = getattr(p, "date", None)
        d_s = d.isoformat() if d is not None and hasattr(d, "isoformat") else str(d or "—")
        src = str(getattr(p, "source", "—") or "—")
        net = getattr(p, "net_val", Decimal("0"))
        lot = getattr(p, "net_lot", 0)
        avg = getattr(p, "avg_price", None)
        try:
            avg_s = f"{float(avg):,.0f}" if avg is not None else "—"
        except (TypeError, ValueError):
            avg_s = "—"
        try:
            lot_s = f"{int(lot):,}"
        except (TypeError, ValueError):
            lot_s = str(lot)
        lines.append(f"{d_s:12}  {src:10}  {_fmt_signed(net):>12}  {lot_s:>10}  {avg_s:>10}")
    lines.append("")
    lines.append("CLI · saham view ticker foreign-history  ·  local cache · browse only")
    return TickerJobText(
        job="foreign",
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · foreign-history",
        body="\n".join(lines),
        empty=False,
        fetch_hint=hint,
        cli_verb="view ticker foreign-history",
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
    fetch_hint: str | None = None,
) -> TickerJobText:
    """Format BrokerDistributionSnapshot (cross-broker counterparties)."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch market {ticker_u}"
    if snapshot is None:
        return TickerJobText(
            job="dist",
            ticker=ticker_u,
            title=f"View · ticker · {ticker_u} · distribution",
            body=f"not cached · broker distribution empty\nHint: {hint}",
            empty=True,
            fetch_hint=hint,
            cli_verb="view ticker distribution",
        )

    d = as_of or getattr(snapshot, "date", None)
    d_s = d.isoformat() if d is not None and hasattr(d, "isoformat") else str(d or "—")
    lines: list[str] = [
        f"Broker distribution · {ticker_u} · {d_s}",
    ]
    if getattr(snapshot, "foreign_buying_from_domestic", False):
        lines.append("★ Foreign accumulating from domestic")
    elif getattr(snapshot, "net_foreign_buyer_dominance", False):
        lines.append("● Foreign brokers dominate buy side")
    lines.append("")

    def _side(entries: Sequence[Any], label: str, arrow: str) -> None:
        if not entries:
            return
        lines.append(label)
        lines.append("─" * 48)
        for entry in list(entries)[:5]:
            code = str(getattr(entry, "broker_code", "—"))
            btype = str(getattr(entry, "broker_type", "") or "")
            amt = int(getattr(entry, "amount_idr", 0) or 0)
            lines.append(f"  {_broker_tag(code, btype):12}  {_fmt_idr_amount(amt):>10}")
            for cp in list(getattr(entry, "counterparties", ()) or ())[:4]:
                cp_code = str(getattr(cp, "broker_code", "—"))
                cp_type = str(getattr(cp, "broker_type", "") or "")
                cp_amt = int(getattr(cp, "amount_idr", 0) or 0)
                pct = (cp_amt / amt * 100) if amt else 0.0
                lines.append(
                    f"    {arrow} {_broker_tag(cp_code, cp_type):12}  "
                    f"{_fmt_idr_amount(cp_amt):>10}  ({pct:.0f}%)"
                )
        lines.append("")

    _side(getattr(snapshot, "top_buyers", ()) or (), "TOP BUYERS  (bought FROM →)", "←")
    _side(getattr(snapshot, "top_sellers", ()) or (), "TOP SELLERS (sold TO →)", "→")
    lines.append("CLI · saham view ticker distribution  ·  local cache · browse only")
    empty = not (getattr(snapshot, "top_buyers", None) or getattr(snapshot, "top_sellers", None))
    return TickerJobText(
        job="dist",
        ticker=ticker_u,
        title=f"View · ticker · {ticker_u} · distribution",
        body="\n".join(lines),
        empty=empty,
        fetch_hint=hint,
        cli_verb="view ticker distribution",
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
