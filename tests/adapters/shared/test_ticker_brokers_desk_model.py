"""Ticker brokers job desk — on-ticker radar, Net3/5/7/10/20, no hero noise."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.shared.ticker_brokers_desk_model import build_ticker_brokers_desk_model
from src.adapters.shared.view_ticker_job_text import format_ticker_brokers_job


def _row(**over: object) -> SimpleNamespace:
    base = dict(
        code="YP",
        type_label="Foreign",
        role="buy",
        as_of="2026-07-31",
        day_net="+1.2B",
        net3="+0.8B",
        net5="+3.0B",
        net7="+4.0B",
        net10="+5.0B",
        net20="+6.0B",
        streak="2",
        delta1="+0.1B",
        has_partial_netx=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_brokers_desk_has_full_net_ladder_and_quiet_hero():
    rows = (
        _row(code="YP"),
        _row(
            code="CC",
            type_label="Local",
            role="sell",
            day_net="-0.5B",
            net3="-0.2B",
            net5="-1.0B",
            net7="-1.1B",
            net10="-1.2B",
            net20="-1.5B",
            streak="0",
            delta1="-0.2B",
            has_partial_netx=True,
        ),
    )
    desk = build_ticker_brokers_desk_model(
        "bbca",
        rows,
        as_of="2026-07-31",
        note="Tracked brokers (not full market top) · Net3/5/7/10/20 stock sessions",
        selected_index=1,
    )
    assert desk.empty is False
    assert desk.ticker == "BBCA"
    assert "STOCK DESKS" in desk.hero_lab
    assert desk.hero_big == "2 desks"
    # Noise rejected from hero
    assert desk.hero_sub == ""
    assert "Tracked brokers" not in desk.hero_sub
    assert "Net3/5" not in desk.hero_sub
    assert desk.story == ""
    # Full Net ladder on rows
    r0 = desk.rows[0]
    assert r0.net3 == "+0.8B"
    assert r0.net5 == "+3.0B"
    assert r0.net7 == "+4.0B"
    assert r0.net10 == "+5.0B"
    assert r0.net20 == "+6.0B"
    text = desk.as_text()
    # Design cockpit headers (not compact Day/N3/R)
    assert "DayNet" in text
    assert "Net3" in text
    assert "Net20" in text
    assert "Role" in text
    assert "sell" in text  # full role word, not "sel"
    assert "+6.0B" in text
    assert "Tracked brokers" not in text


def test_format_ticker_brokers_job_attaches_desk_and_rows():
    rows = (_row(code="YP"),)
    text = format_ticker_brokers_job(
        "UNVR",
        rows,
        as_of="2026-07-31",
        note="Tracked brokers (not full market top)",
    )
    assert text.job == "brokers"
    assert text.desk is not None
    assert text.desk.hero_sub == ""
    assert "Tracked brokers" not in text.body
    assert text.broker_rows
    assert text.cli_verb == "view ticker top-brokers"
    assert "YP" in text.body
    assert text.desk.rows[0].net20 == "+6.0B"
