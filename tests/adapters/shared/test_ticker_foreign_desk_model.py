"""Ticker foreign-history desk model — real points only, design hero/pulses/days."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.shared.ticker_foreign_desk_model import (
    build_ticker_foreign_desk_model,
    empty_ticker_foreign_desk,
)
from src.adapters.shared.view_ticker_job_text import format_ticker_foreign_history_job


def _pt(
    d: date,
    net: str,
    *,
    lot: int = 0,
    avg: str = "1000",
    source: str = "stockbit",
) -> SimpleNamespace:
    return SimpleNamespace(
        date=d,
        net_val=Decimal(net),
        net_lot=lot,
        avg_price=Decimal(avg),
        source=source,
    )


def test_foreign_desk_hero_pulses_days_from_real_points():
    pts = (
        _pt(date(2026, 7, 25), "1000000000", lot=100, avg="6200"),
        _pt(date(2026, 7, 28), "-500000000", lot=-50, avg="6225"),
        _pt(date(2026, 7, 29), "-27800000000", lot=-1000, avg="6275"),
    )
    desk = build_ticker_foreign_desk_model(
        "bbca",
        pts,
        resolved_source="stockbit",
        window_days=30,
        as_of=date(2026, 7, 29),
    )
    assert desk.empty is False
    assert desk.ticker == "BBCA"
    assert desk.hero_lab == "FOREIGN HISTORY"
    # Hero = latest day net
    assert desk.hero_big.startswith("-") or desk.hero_big.startswith("−")
    assert desk.hero_tone == "neg"
    assert "source=stockbit" in desk.hero_sub
    assert "foreign net only" in desk.hero_sub
    # Pulses: 5d · 20d · days · source
    assert desk.pulses[0].label == "5d net"
    assert desk.pulses[1].label == "20d net"
    assert desk.pulses[2].value == "3"
    assert desk.pulses[3].value == "stockbit"
    # 5d = sum of all 3 (window shorter than 5)
    assert desk.pulses[0].tone == "neg"
    # Newest first
    assert desk.days[0].date_s == "2026-07-29"
    assert desk.days[0].source == "stockbit"
    assert desk.days[0].lot_s == "-1,000"
    assert desk.days[0].avg_s == "6,275"
    assert desk.days[0].bar_pct == 100
    assert "point series" in desk.story.lower() or "Point series" in desk.story
    text = desk.as_text()
    assert "Action" not in text
    assert "ENTER" not in text


def test_foreign_desk_empty_honest():
    desk = build_ticker_foreign_desk_model("UNVR", ())
    assert desk.empty is True
    assert desk.hero_big == "—"
    assert desk.days == ()


def test_empty_ticker_foreign_desk_helper():
    desk = empty_ticker_foreign_desk("TLKM")
    assert desk.ticker == "TLKM"
    assert desk.empty is True


def test_format_ticker_foreign_history_job_attaches_desk():
    text = format_ticker_foreign_history_job(
        "UNVR",
        (
            _pt(date(2026, 7, 31), "8319156000", lot=47613, avg="1734.8"),
            _pt(date(2026, 7, 30), "3503186000", lot=20502, avg="1706.6"),
        ),
        resolved_source="stockbit",
        window_days=30,
        as_of=date(2026, 7, 31),
    )
    assert text.job == "foreign"
    assert text.desk is not None
    assert text.desk.hero_big.startswith("+")
    assert text.desk.days[0].date_s == "2026-07-31"
    assert "2026-07-31" in text.body
    assert "foreign-history" in text.cli_verb
