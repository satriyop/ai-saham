"""Ticker brokers job desk — on-ticker radar, not independent stage."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.shared.ticker_brokers_desk_model import build_ticker_brokers_desk_model
from src.adapters.shared.view_ticker_job_text import format_ticker_brokers_job


def test_brokers_desk_rows_and_selection():
    rows = (
        SimpleNamespace(
            code="YP",
            type_label="Foreign",
            role="buy",
            as_of="2026-07-31",
            day_net="+1.2B",
            net5="+3.0B",
            streak="2",
            delta1="+0.1B",
            has_partial_netx=False,
        ),
        SimpleNamespace(
            code="CC",
            type_label="Local",
            role="sell",
            as_of="2026-07-31",
            day_net="-0.5B",
            net5="-1.0B",
            streak="0",
            delta1="-0.2B",
            has_partial_netx=True,
        ),
    )
    desk = build_ticker_brokers_desk_model(
        "bbca",
        rows,
        as_of="2026-07-31",
        note="summary tops",
        selected_index=1,
    )
    assert desk.empty is False
    assert desk.ticker == "BBCA"
    assert "STOCK DESKS" in desk.hero_lab
    assert desk.pulses[0].value == "2"
    assert desk.rows[1].code == "CC"
    assert desk.selected_index == 1
    assert "›" in desk.as_text()
    assert "CC" in desk.as_text()


def test_format_ticker_brokers_job_attaches_desk_and_rows():
    rows = (
        SimpleNamespace(
            code="YP",
            type_label="Foreign",
            role="buy",
            as_of="2026-07-31",
            day_net="+1B",
            net5="+2B",
            streak="1",
            delta1="+0",
            has_partial_netx=False,
        ),
    )
    text = format_ticker_brokers_job("UNVR", rows, as_of="2026-07-31")
    assert text.job == "brokers"
    assert text.desk is not None
    assert text.broker_rows
    assert text.cli_verb == "view ticker top-brokers"
    assert "YP" in text.body
