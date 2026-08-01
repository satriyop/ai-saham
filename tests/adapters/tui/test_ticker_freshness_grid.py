"""View ticker freshness strip — real state only, no Sent."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.tui.ticker_desk_model import FRESH_GRID_LABELS, _freshness_pills


def test_fresh_grid_labels_exclude_sent():
    assert "Sent" not in FRESH_GRID_LABELS
    assert "Sentiment" not in FRESH_GRID_LABELS


def test_freshness_pills_drop_sentiment_and_do_not_pad_fake_miss():
    items = (
        SimpleNamespace(label="Price", status=SimpleNamespace(value="ok")),
        SimpleNamespace(label="Flow", status=SimpleNamespace(value="stale")),
        SimpleNamespace(label="Sentiment", status=SimpleNamespace(value="ok")),
        SimpleNamespace(label="sent", status=SimpleNamespace(value="missing")),
    )
    pills = _freshness_pills(items)
    labels = [p.label for p in pills]
    assert labels == ["Price", "Flow"]
    assert all(p.label != "Sent" for p in pills)
    # No invented Analyst/Own/… miss tiles
    assert len(pills) == 2
    assert pills[0].status == "ok"
    assert pills[1].status == "stale"


def test_freshness_pills_empty_when_no_items():
    assert _freshness_pills(()) == []
    assert _freshness_pills(None) == []


def test_freshness_pills_order_follows_known_grid():
    items = (
        SimpleNamespace(label="Insider", status=SimpleNamespace(value="ok")),
        SimpleNamespace(label="Price", status=SimpleNamespace(value="ok")),
        SimpleNamespace(label="Bandar", status=SimpleNamespace(value="missing")),
    )
    pills = _freshness_pills(items)
    assert [p.label for p in pills] == ["Price", "Bandar", "Insider"]
    assert pills[1].status == "miss"


def test_horizon_bar_glyphs_no_hollow_wallpaper():
    """Ticker horizons: filled blocks only — no grey ░ fake fill."""
    from src.adapters.tui.ticker_desk_model import bar_glyphs

    assert bar_glyphs(0, width=8, hollow=False) == ""
    solid = bar_glyphs(50, width=8, hollow=False)
    assert "░" not in solid
    assert "█" in solid
    hollow = bar_glyphs(50, width=8, hollow=True)
    assert "░" in hollow


def test_earnings_yoy_uses_domain_pct_not_idr_delta():
    """eps_yoy_change is IDR — YoY display must use growth %, not that field as %."""
    from datetime import datetime

    from src.adapters.tui.ticker_desk_model import _earnings_rows, bar_glyphs
    from src.domain.value_objects.earnings_record import EarningsRecord

    # Q4 2025 EPS 112.9 vs prior year ~9.41 → ~+1099% is correct math from fields
    # but extreme → warn tone + * (likely split / non-comparable base)
    rec = EarningsRecord(
        ticker="UNVR",
        year=2025,
        quarter=4,
        eps_actual=112.9,
        eps_estimate=None,
        eps_surprise_pct=None,
        eps_yoy_change=103.5,  # IDR delta — must NOT become +103.5%
        eps_prev_year=9.41,
        fetched_at=datetime(2026, 1, 1),
    )
    rows = _earnings_rows([rec])
    assert len(rows) == 1
    assert rows[0].period == "Q4 2025"
    assert rows[0].eps == "112.9"
    # Domain: (112.9 - 9.41) / 9.41 * 100 ≈ 1099.8 — not the IDR delta as %
    assert rows[0].yoy.startswith("+")
    assert "1099" in rows[0].yoy or "1100" in rows[0].yoy
    assert rows[0].yoy.endswith("*")
    assert rows[0].yoy_tone == "warn"
    assert rows[0].yoy_extreme is True
    # Relative bar full for sole max eps; no hollow glyph in earnings paint path
    assert rows[0].bar_pct == 100
    assert "░" not in bar_glyphs(rows[0].bar_pct, width=12, hollow=False)


def test_earnings_yoy_negative_from_prev_year():
    from src.adapters.tui.ticker_desk_model import _earnings_rows
    from src.domain.value_objects.earnings_record import EarningsRecord

    rec = EarningsRecord(
        ticker="UNVR",
        year=2026,
        quarter=2,
        eps_actual=21.7,
        eps_estimate=None,
        eps_surprise_pct=None,
        eps_yoy_change=-2.3,
        eps_prev_year=24.0,
        fetched_at=None,
    )
    rows = _earnings_rows([rec])
    assert rows[0].yoy_tone == "neg"
    assert rows[0].yoy.startswith("−") or rows[0].yoy.startswith("-")
    assert rows[0].yoy_extreme is False
    assert not rows[0].yoy.endswith("*")


def test_earnings_dedupes_same_quarter_snapshots():
    from src.adapters.tui.ticker_desk_model import _earnings_rows
    from src.domain.value_objects.earnings_record import EarningsRecord

    a = EarningsRecord(
        ticker="UNVR",
        year=2026,
        quarter=1,
        eps_actual=56.11,
        eps_estimate=None,
        eps_surprise_pct=None,
        eps_yoy_change=73.02,
        eps_prev_year=32.43,
        fetched_at=None,
    )
    b = EarningsRecord(
        ticker="UNVR",
        year=2026,
        quarter=1,
        eps_actual=56.11,
        eps_estimate=None,
        eps_surprise_pct=None,
        eps_yoy_change=73.02,
        eps_prev_year=32.43,
        fetched_at=None,
    )
    rows = _earnings_rows([a, b])
    assert len(rows) == 1
    assert rows[0].period == "Q1 2026"
