"""Brass [k] keycap paint on FlagChip (design navigation dialect)."""

from __future__ import annotations

from src.adapters.tui.widgets.chip_bar import (
    TICKER_JOB_FLAG_POWER,
    TICKER_JOB_POWER_KEYS,
    power_key_for_flag,
)
from src.adapters.tui.widgets.flag_chip import FlagChip, format_chip_markup


def test_format_chip_markup_brass_idle_and_dark_on():
    idle = format_chip_markup("brokers", power_key="b", is_on=False)
    assert "[b]" in idle
    assert "brokers" in idle
    assert "#d4b06a" in idle  # brass
    on = format_chip_markup("brokers", power_key="b", is_on=True)
    assert "[b]" in on
    assert "#1a120c" in on  # dark on peach
    assert "#d4b06a" not in on


def test_ticker_power_map_covers_all_job_chips():
    assert set(TICKER_JOB_POWER_KEYS.values()) == set(TICKER_JOB_FLAG_POWER)
    assert power_key_for_flag("brokers") == "b"
    assert power_key_for_flag("foreign") == "o"
    assert power_key_for_flag("detail") == "d"
    assert power_key_for_flag("t") == "t"


def test_flag_chip_paints_keycap_and_preserves_flag_key():
    chip = FlagChip("brokers", "brokers", power_key="b", id="td-flag-brokers")
    assert chip.flag_key == "brokers"
    assert chip.power_key == "b"
    chip.set_chip_state(available=True, expanded=False)
    assert chip._word == "brokers"
    chip.set_chip_state(available=True, expanded=True)
    assert chip._expanded is True


def test_flag_chip_parses_legacy_bracket_label():
    chip = FlagChip("detail", "[d] detail", id="x")
    assert chip._word == "detail"
    assert chip.power_key == "d"
