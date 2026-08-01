"""Ticker flow desk model — real summaries only, design hero/pulses/days."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.shared.ticker_flow_desk_model import (
    build_ticker_flow_desk_model,
    empty_ticker_flow_desk,
)
from src.adapters.shared.view_ticker_job_text import format_ticker_flow_job


def _summ(
    d: date,
    net: str,
    *,
    ratio: str = "5.0",
    buy: bool = False,
    buyer: str | None = None,
    seller: str | None = None,
) -> SimpleNamespace:
    buyers = (SimpleNamespace(broker_code=buyer),) if buyer else ()
    sellers = (SimpleNamespace(broker_code=seller),) if seller else ()
    return SimpleNamespace(
        date=d,
        foreign_net_value=Decimal(net),
        foreign_flow_ratio=Decimal(ratio),
        is_foreign_accumulating=buy,
        top_buyers=buyers,
        top_sellers=sellers,
        source="idx",
    )


def test_flow_desk_hero_pulses_days_from_real_summaries():
    rows = (
        _summ(date(2026, 7, 28), "-1000000000", ratio="12.5", buy=False, buyer="YP", seller="AK"),
        _summ(date(2026, 7, 29), "500000000", ratio="8.0", buy=True, buyer="CC"),
        _summ(date(2026, 7, 30), "2000000000", ratio="10.0", buy=True, buyer="YP", seller="XL"),
    )
    desk = build_ticker_flow_desk_model(
        "bbca",
        rows,
        total_net=Decimal("1500000000"),
        buy_days=2,
        sell_days=1,
        window_days=10,
        source="idx",
        as_of=date(2026, 7, 30),
    )
    assert desk.empty is False
    assert desk.ticker == "BBCA"
    assert "FOREIGN FLOW · 10d" in desk.hero_lab
    assert desk.hero_big.startswith("+")
    assert desk.hero_tone == "pos"
    assert "broker_summaries" in desk.hero_sub
    assert "2026-07-30" in desk.hero_sub
    assert desk.source == "idx"
    # Pulses: buy / sell / consec / latest
    assert desk.pulses[0].value == "2"
    assert desk.pulses[1].value == "1"
    assert desk.pulses[2].value == "2"  # consec buy from newest
    assert desk.pulses[3].value.startswith("+")
    # Newest first
    assert desk.days[0].date_s == "2026-07-30"
    assert desk.days[-1].date_s == "2026-07-28"
    assert desk.days[0].buyer == "YP"
    assert desk.days[1].seller == "—"  # honest empty top seller
    # Relative bar on largest |net|
    assert desk.days[0].bar_pct == 100
    assert all(d.bar_pct >= 1 for d in desk.days)
    # No Action / no fake
    text = desk.as_text()
    assert "Action" not in text
    assert "ENTER" not in text
    # Scalar bar contract: of-max % label present (same basis as bar_pct)
    assert "OfMax" in text
    assert "100%" in text


def test_flow_desk_empty_honest():
    desk = build_ticker_flow_desk_model("UNVR", ())
    assert desk.empty is True
    assert desk.hero_big == "—"
    assert "not cached" in desk.hero_sub.lower() or "empty" in desk.hero_sub.lower()
    assert desk.days == ()


def test_empty_ticker_flow_desk_helper():
    desk = empty_ticker_flow_desk("TLKM")
    assert desk.ticker == "TLKM"
    assert desk.empty is True


def test_format_ticker_flow_job_attaches_desk():
    text = format_ticker_flow_job(
        "UNVR",
        (
            _summ(date(2026, 7, 30), "7428179500", ratio="45.6", buy=True),
            _summ(date(2026, 7, 29), "-1000000000", ratio="5.0", buy=False),
        ),
        total_net=Decimal("6428179500"),
        buy_days=1,
        sell_days=1,
        window_days=10,
        source="idx",
        as_of=date(2026, 7, 30),
    )
    assert text.job == "flow"
    assert text.desk is not None
    assert text.desk.hero_big.startswith("+")
    assert text.desk.days[0].date_s == "2026-07-30"
    # Honest dash when no top desks in cache
    assert text.desk.days[0].buyer == "—"
    assert "2026-07-30" in text.body
