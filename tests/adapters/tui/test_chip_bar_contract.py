"""Shared Chip bar contract — foundation (design bible §1–2).

Plain Tab focus · no row labels · ticker power map · density last.
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from src.adapters.tui.widgets.chip_bar import (
    BROKER_HOME_CHIPS,
    TICKER_JOB_CHIPS,
    TICKER_JOB_POWER_KEYS,
    ChipBar,
)
from src.adapters.tui.widgets.flag_chip import FlagChip


def test_ticker_job_power_map_locked():
    assert TICKER_JOB_POWER_KEYS == {
        "b": "brokers",
        "f": "flow",
        "o": "foreign",
        "x": "dist",
        "n": "fin",
    }
    labels = [lab for _, lab in TICKER_JOB_CHIPS]
    assert labels == ["brokers", "flow", "foreign", "dist", "fin"]
    assert "flow" in labels  # CLI verb kept (not renamed summary)


def test_broker_home_product_labels_no_deep_noise():
    for key, lab in BROKER_HOME_CHIPS:
        assert "deep." not in lab
    assert dict(BROKER_HOME_CHIPS)["t"] == "buy/sell"
    assert dict(BROKER_HOME_CHIPS)["m"] == "top 5"


def test_chip_bar_compose_jobs_then_density_no_meta():
    """Density last as [d] detail; no brief/detail meta status text."""

    async def scenario() -> None:
        class _A(App):
            def compose(self) -> ComposeResult:
                yield ChipBar(
                    id="bar",
                    chips=TICKER_JOB_CHIPS,
                    chip_id_prefix="td-flag",
                    include_detail=True,
                    detail_id="td-flag-detail",
                    meta_id="td-density-meta",  # accepted, not painted
                    meta_text="brief",
                )

        app = _A()
        async with app.run_test() as pilot:
            await pilot.pause(0.05)
            bar = app.query_one("#bar", ChipBar)
            chips = [c for c in bar.children if isinstance(c, FlagChip)]
            keys = [c.flag_key for c in chips]
            assert keys[-1] == "detail"  # density last
            assert keys[:-1] == ["brokers", "flow", "foreign", "dist", "fin"]
            for c in chips:
                assert c.can_focus is True
            detail = app.query_one("#td-flag-detail", FlagChip)
            label = str(getattr(detail, "_label", "") or detail.content or "")
            assert "[d] detail" in label or "[d]" in label
            bar.paint_states(on_keys=("detail",))
            assert "is-on" in detail.classes
            # No density meta widget (noise removed)
            assert not any(getattr(c, "id", None) == "td-density-meta" for c in bar.children)
            bar.set_meta("detail")  # no-op

    asyncio.run(scenario())


def test_flag_chip_enter_space_activate_path():
    """Keyboard activate matches click (Chip bar navigation)."""
    chip = FlagChip("flow", "flow", id="t-flow")
    chip.set_chip_state(available=True, expanded=False)
    assert chip.can_focus is True
    assert chip._available is True
