"""Ticker financials job desk — design: tui-cockpit-opencode.md §fin.

Hero · pulses · three cards (income · balance · cashflow) from real
``ViewTickerFinancialsUseCase``. Always show three cards; honest empty per kind.
No full spreadsheet · no Action.

Layer: Adapter shared (pure presentation · CLI + TUI)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FinPulse:
    key: str
    label: str
    value: str
    tone: str = "neutral"


@dataclass(frozen=True)
class FinMetricRow:
    label: str
    value: str


@dataclass(frozen=True)
class FinCard:
    kind: str  # income | balance | cashflow
    title: str
    status: str  # ok | empty
    period_label: str  # latest period or —
    source: str
    rows: tuple[FinMetricRow, ...]  # latest period metrics
    history: tuple[str, ...]  # compact prior period lines (≤3)
    empty_hint: str = ""


@dataclass(frozen=True)
class TickerFinDeskModel:
    """Structured financials job surface (three cards under chip bar)."""

    ticker: str
    title: str
    empty: bool
    fetch_hint: str
    cli_verb: str
    hero_lab: str
    hero_big: str
    hero_tone: str
    hero_sub: str
    story: str
    pulses: tuple[FinPulse, ...]
    cards: tuple[FinCard, FinCard, FinCard]
    footer: str

    def as_text(self) -> str:
        if self.empty and all(c.status != "ok" for c in self.cards):
            return f"{self.title}\n\nnot cached · no financial statements\nHint: {self.fetch_hint}"
        lines = [
            self.title,
            "",
            f"{self.hero_lab}  {self.hero_big}",
            self.hero_sub,
            "",
        ]
        for c in self.cards:
            lines.append(f"── {c.title} · {c.period_label} ──")
            if c.status != "ok":
                lines.append(f"  {c.empty_hint or 'not cached'}")
            else:
                for m in c.rows:
                    lines.append(f"  {m.label:8} {m.value}")
                for h in c.history:
                    lines.append(f"  {h}")
            lines.append("")
        lines.append(self.footer)
        return "\n".join(lines)


def _fmt_fin_idr(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
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
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _period_label(period: Any, *, period_type: str = "quarter") -> str:
    pe = getattr(period, "period_end", None)
    if pe is None:
        return "—"
    grain = (period_type or "quarter").strip().lower()
    if grain == "annual" and hasattr(pe, "year"):
        return f"FY {int(pe.year)}"
    if hasattr(pe, "month") and hasattr(pe, "year"):
        q = (int(pe.month) - 1) // 3 + 1
        return f"Q{q} {pe.year}"
    if hasattr(pe, "isoformat"):
        return str(pe.isoformat())[:10]
    return str(pe)[:10]


def _date_s(period: Any) -> str:
    pe = getattr(period, "period_end", None)
    if pe is None:
        return "—"
    if hasattr(pe, "isoformat"):
        return str(pe.isoformat())[:10]
    return str(pe)[:10]


def _income_metrics(p: Any) -> tuple[FinMetricRow, ...]:
    return (
        FinMetricRow("Revenue", _fmt_fin_idr(getattr(p, "total_revenue", None))),
        FinMetricRow("NI", _fmt_fin_idr(getattr(p, "net_income", None))),
        FinMetricRow("EPS", _fmt_eps(getattr(p, "eps_basic", None))),
    )


def _balance_metrics(p: Any) -> tuple[FinMetricRow, ...]:
    return (
        FinMetricRow("Assets", _fmt_fin_idr(getattr(p, "total_assets", None))),
        FinMetricRow("Equity", _fmt_fin_idr(getattr(p, "stockholders_equity", None))),
        FinMetricRow("Debt", _fmt_fin_idr(getattr(p, "total_debt", None))),
    )


def _cashflow_metrics(p: Any) -> tuple[FinMetricRow, ...]:
    return (
        FinMetricRow("Op CF", _fmt_fin_idr(getattr(p, "operating_cash_flow", None))),
        FinMetricRow("FCF", _fmt_fin_idr(getattr(p, "free_cash_flow", None))),
        FinMetricRow("CapEx", _fmt_fin_idr(getattr(p, "capital_expenditure", None))),
    )


def _history_lines(
    kind: str,
    periods: Sequence[Any],
    *,
    skip_first: bool = True,
) -> tuple[str, ...]:
    items = list(periods or ())
    if skip_first:
        items = items[1:]
    out: list[str] = []
    for p in items[:3]:
        pe = _date_s(p)
        if kind == "income":
            out.append(
                f"{pe}  rev {_fmt_fin_idr(getattr(p, 'total_revenue', None))}  "
                f"ni {_fmt_fin_idr(getattr(p, 'net_income', None))}"
            )
        elif kind == "balance":
            out.append(f"{pe}  assets {_fmt_fin_idr(getattr(p, 'total_assets', None))}")
        else:
            out.append(f"{pe}  op {_fmt_fin_idr(getattr(p, 'operating_cash_flow', None))}")
    return tuple(out)


def _card_from_result(result: Any | None, *, kind: str, hint: str) -> FinCard:
    titles = {
        "income": "INCOME",
        "balance": "BALANCE",
        "cashflow": "CASHFLOW",
    }
    title = titles.get(kind, kind.upper())
    if result is None:
        return FinCard(
            kind=kind,
            title=title,
            status="empty",
            period_label="—",
            source="—",
            rows=(),
            history=(),
            empty_hint=f"not cached · {hint}",
        )
    status = str(getattr(result, "status", "empty") or "empty")
    periods = list(getattr(result, "periods", ()) or ())
    src = str(getattr(result, "source", None) or "—")
    grain = str(getattr(result, "period_type", "quarter") or "quarter").strip().lower()
    if status != "ok" or not periods:
        msg = getattr(result, "message", None) or f"No {kind} periods cached"
        return FinCard(
            kind=kind,
            title=title,
            status="empty",
            period_label="—",
            source=src,
            rows=(),
            history=(),
            empty_hint=str(msg),
        )
    latest = periods[0]
    if kind == "income":
        metrics = _income_metrics(latest)
    elif kind == "balance":
        metrics = _balance_metrics(latest)
    else:
        metrics = _cashflow_metrics(latest)
    return FinCard(
        kind=kind,
        title=title,
        status="ok",
        period_label=_period_label(latest, period_type=grain),
        source=src,
        rows=metrics,
        history=_history_lines(kind, periods, skip_first=True),
        empty_hint="",
    )


def build_ticker_fin_desk_model(
    ticker: str,
    results: Sequence[Any],
    *,
    fetch_hint: str | None = None,
) -> TickerFinDeskModel:
    """Build fin desk from income/balance/cashflow use-case results."""
    ticker_u = str(ticker).upper()
    hint = fetch_hint or f"saham fetch financials {ticker_u}"
    title = f"View · ticker · {ticker_u} · financials"
    story = "Three statements · latest period metrics · local cache · not Action."

    by_kind: dict[str, Any] = {}
    for r in results or ():
        k = str(getattr(r, "statement", "") or "").lower()
        if k in {"income", "balance", "cashflow"}:
            by_kind[k] = r

    income = _card_from_result(by_kind.get("income"), kind="income", hint=hint)
    balance = _card_from_result(by_kind.get("balance"), kind="balance", hint=hint)
    cashflow = _card_from_result(by_kind.get("cashflow"), kind="cashflow", hint=hint)
    cards = (income, balance, cashflow)

    any_ok = any(c.status == "ok" for c in cards)
    empty = not any_ok

    # Hero from latest income period when present (grain once — not a second control)
    period_type = "quarter"
    for r in (by_kind.get("income"), by_kind.get("balance"), by_kind.get("cashflow")):
        if r is not None:
            period_type = str(getattr(r, "period_type", "quarter") or "quarter")
            break
    if income.status == "ok":
        hero_big = income.period_label
        src = income.source
        hero_sub = f"{period_type} · source={src} · local cache"
    else:
        hero_big = "—"
        hero_sub = f"not cached · Hint: {hint}" if empty else "partial cache · local"

    ok_n = sum(1 for c in cards if c.status == "ok")
    pulses = (
        FinPulse("inc", "Income", "ok" if income.status == "ok" else "—"),
        FinPulse("bal", "Balance", "ok" if balance.status == "ok" else "—"),
        FinPulse("cf", "Cashflow", "ok" if cashflow.status == "ok" else "—"),
        FinPulse("n", "Cards", f"{ok_n}/3"),
    )
    # Footer: y period when grain is in play (chip bar owns the control)
    footer = (
        "esc show · y period · chips switch · "
        "CLI · saham view ticker financials --period quarterly|annual · browse only"
    )

    return TickerFinDeskModel(
        ticker=ticker_u,
        title=title,
        empty=empty,
        fetch_hint=hint,
        cli_verb="view ticker financials",
        hero_lab="FINANCIALS",
        hero_big=hero_big,
        hero_tone="neutral",
        hero_sub=hero_sub,
        story=story,
        pulses=pulses,
        cards=cards,
        footer=footer,
    )
