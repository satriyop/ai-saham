"""Soft VWAP depth badge helpers — display-only, not scoring policy."""

from __future__ import annotations

import pytest

from src.adapters.cli.screen_accum_formatters import (
    format_disc_pct,
    format_disc_pct_plain,
    vwap_depth_label,
)


@pytest.mark.parametrize(
    ("pct", "expected"),
    [
        (None, None),
        (10.0, "deep"),
        (8.0, "deep"),
        (7.99, "mid"),
        (3.0, "mid"),
        (2.99, "shallow"),
        (0.0, "shallow"),
        (-0.1, "over"),
        (-5.0, "over"),
    ],
)
def test_vwap_depth_label_bands(pct, expected):
    assert vwap_depth_label(pct) == expected


def test_format_disc_pct_plain_includes_badge():
    assert format_disc_pct_plain(9.2) == "+9.2% deep"
    assert format_disc_pct_plain(4.1) == "+4.1% mid"
    assert format_disc_pct_plain(1.0) == "+1.0% shallow"
    assert format_disc_pct_plain(-2.3) == "-2.3% over"
    assert format_disc_pct_plain(None) == "—"


def test_format_disc_pct_rich_uses_color_bands_without_suffix():
    """CLI table keeps bare +pct so Phase/Next columns fit width=100."""
    text = format_disc_pct(9.2)
    assert text.plain == "+9.2%"
    assert "bold green" in text.style
    over = format_disc_pct(-1.5)
    assert over.plain == "-1.5%"
    assert over.style == "red"
    mid = format_disc_pct(4.0)
    assert mid.plain == "+4.0%"
    assert mid.style == "yellow"
    shallow = format_disc_pct(1.0)
    assert shallow.plain == "+1.0%"
    assert shallow.style == "bright_black"
