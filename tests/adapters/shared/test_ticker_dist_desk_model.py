"""Ticker distribution desk model — real snapshot only, F/L tags, dual heat."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.adapters.shared.ticker_dist_desk_model import (
    build_ticker_dist_desk_model,
    type_tag,
)
from src.adapters.shared.view_ticker_job_text import format_ticker_distribution_job


def test_type_tag_never_asing_a():
    assert type_tag("Asing") == "F"
    assert type_tag("foreign") == "F"
    assert type_tag("Lokal") == "L"
    assert type_tag("Pemerintah") == "G"
    assert type_tag("") == "L"
    assert "A" not in {type_tag("Asing"), type_tag("Lokal")}


def test_dist_desk_hero_pulses_sides_from_snapshot():
    snap = SimpleNamespace(
        date=date(2026, 7, 31),
        foreign_buying_from_domestic=True,
        net_foreign_buyer_dominance=False,
        top_buyers=(
            SimpleNamespace(
                broker_code="RX",
                broker_type="Asing",
                amount_idr=12_875_381_000,
                counterparties=(
                    SimpleNamespace(
                        broker_code="LG",
                        broker_type="Lokal",
                        amount_idr=6_000_000_000,
                    ),
                    SimpleNamespace(
                        broker_code="AK",
                        broker_type="Asing",
                        amount_idr=3_000_000_000,
                    ),
                ),
            ),
            SimpleNamespace(
                broker_code="LG",
                broker_type="Lokal",
                amount_idr=6_254_209_500,
                counterparties=(),
            ),
        ),
        top_sellers=(
            SimpleNamespace(
                broker_code="ZP",
                broker_type="Asing",
                amount_idr=7_995_500_500,
                counterparties=(),
            ),
        ),
    )
    desk = build_ticker_dist_desk_model(
        "unvr",
        snap,
        as_of=date(2026, 7, 31),
        source="broker_distribution_cache",
    )
    assert desk.empty is False
    assert desk.ticker == "UNVR"
    assert "DISTRIBUTION · UNVR" in desk.hero_lab
    assert "Foreign buying from domestic" in desk.hero_big
    assert desk.hero_tone == "pos"
    assert "2026-07-31" in desk.hero_sub
    assert desk.pulses[0].value == "2"
    assert desk.pulses[1].value == "1"
    assert "RX" in desk.pulses[2].value
    assert desk.buyers[0].code == "RX"
    assert desk.buyers[0].type_tag == "F"  # never A
    assert desk.buyers[0].cps[0].type_tag == "L"
    assert desk.buyers[0].cps[0].pct > 0
    assert desk.sellers[0].type_tag == "F"
    text = desk.as_text()
    assert "Action" not in text or "not Action" in desk.hero_sub
    assert "[A]" not in text


def test_dist_desk_empty_honest():
    desk = build_ticker_dist_desk_model("BBCA", None)
    assert desk.empty is True
    assert desk.buyers == ()
    assert desk.hero_big == "—"


def test_format_ticker_distribution_job_attaches_desk():
    snap = SimpleNamespace(
        date=date(2026, 7, 31),
        foreign_buying_from_domestic=False,
        net_foreign_buyer_dominance=False,
        top_buyers=(
            SimpleNamespace(
                broker_code="YP",
                broker_type="Asing",
                amount_idr=1_000_000_000,
                counterparties=(),
            ),
        ),
        top_sellers=(),
    )
    text = format_ticker_distribution_job(
        "BBCA",
        snap,
        as_of=date(2026, 7, 31),
        source="broker_distribution_cache",
    )
    assert text.job == "dist"
    assert text.desk is not None
    assert text.desk.buyers[0].type_tag == "F"
    assert "YP[F]" in text.body
    assert "Asing" not in text.body or "Foreign" in text.desk.story
