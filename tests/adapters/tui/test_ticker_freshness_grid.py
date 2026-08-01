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
