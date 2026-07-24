"""Unit tests for ticker dashboard panel layout / brief mode."""

from src.adapters.cli.view_ticker_layout import (
    BRIEF_PANEL_KEYS,
    FULL_PANEL_ORDER,
    panel_keys_for_mode,
    should_render_panel,
)


def test_full_mode_includes_all_panels_in_order():
    keys = panel_keys_for_mode(brief=False)
    assert keys == FULL_PANEL_ORDER
    assert "profile" in keys
    assert "candles" in keys
    assert "sentiment" in keys


def test_brief_mode_is_ordered_subset():
    keys = panel_keys_for_mode(brief=True)
    assert set(keys) == BRIEF_PANEL_KEYS
    # Preserve relative order from full layout.
    full_index = {k: i for i, k in enumerate(FULL_PANEL_ORDER)}
    assert list(keys) == sorted(keys, key=lambda k: full_index[k])
    assert "identity" in keys
    assert "price_structure" in keys
    assert "foreign_flow" in keys
    assert "candles" not in keys
    assert "profile" not in keys
    assert "sentiment" not in keys


def test_should_render_panel_respects_brief_flag():
    assert should_render_panel("earnings", brief=True) is True
    assert should_render_panel("ownership", brief=True) is False
    assert should_render_panel("ownership", brief=False) is True
