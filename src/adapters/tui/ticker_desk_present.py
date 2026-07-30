"""Harga-mast ticker desk presentation (design: tui-ticker-desk.html).

Cache dashboard only — never Action / ENTER / WATCH / AVOID.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any


def format_harga_mast(
    *,
    ticker: str,
    price: str,
    as_of: str = "—",
    change_line: str = "",
    authority: str = "cache dashboard · not Action",
) -> str:
    """Hero block: monumental price first."""
    t = (ticker or "—").strip().upper() or "—"
    p = (price or "—").strip() or "—"
    lines = [
        f"[bold #e8e8e8]View · ticker · {t}[/]",
        "[bold #e8b86d]HARGA MAST[/]",
        f"[bold #faf6ee]{p}[/]",
    ]
    if change_line:
        lines.append(f"[#8b92a0]{change_line}[/]")
    lines.append(f"[#5c6575]as_of {as_of or '—'} · {authority}[/]")
    lines.append("[dim]not Action authority · local cache only · v b desks[/]")
    lines.append("")
    return "\n".join(lines)


def format_ticker_desk_from_dashboard(dashboard: Any, *, body: str = "") -> str:
    """Harga mast + optional full dashboard body text."""
    ticker = str(getattr(dashboard, "ticker", "?") or "?")
    close = getattr(dashboard, "latest_close", None)
    if close is not None:
        try:
            price = f"{int(round(float(close))):,}"
        except (TypeError, ValueError):
            price = str(close)
    else:
        price = "—"
    as_of = getattr(dashboard, "as_of", None)
    as_of_s = str(as_of)[:10] if as_of is not None else "—"
    ps = getattr(dashboard, "price_structure", None)
    change = ""
    if ps is not None:
        # best-effort duck fields; never invent Action
        for attr in ("day_change_pct", "change_pct", "pct_change"):
            v = getattr(ps, attr, None)
            if v is not None:
                try:
                    change = f"Δ {float(v):+.2f}%"
                except (TypeError, ValueError):
                    change = f"Δ {v}"
                break
    mast = format_harga_mast(
        ticker=ticker,
        price=price,
        as_of=as_of_s,
        change_line=change,
    )
    if body and body.strip():
        return mast + body.strip() + "\n"
    return mast


def format_ticker_desk_from_text(*, ticker: str, body: str) -> str:
    """When loader only has preformatted text: prepend mast with best-effort price parse."""
    price = _guess_price_from_body(body) or "—"
    mast = format_harga_mast(ticker=ticker, price=price, as_of="—")
    return mast + (body or "")


def _guess_price_from_body(body: str) -> str | None:
    """Light heuristic for last/close numbers in dashboard text — display only."""
    import re

    if not body:
        return None
    # Prefer lines with Close / Last / Price
    for pat in (
        r"(?:Close|Last|Price|Harga)\s*[:=]?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)",
        r"\b([0-9]{1,3}(?:,[0-9]{3})+)\b",
    ):
        m = re.search(pat, body, re.I)
        if m:
            return m.group(1)
    return None
