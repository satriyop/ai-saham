"""Tests for PolicyRateStep pure helpers."""

from datetime import date

import pytest

from src.domain.value_objects.policy_rate_step import (
    PolicyRateDirection,
    PolicyRateStep,
    direction_from_actual_previous,
    parse_rate_number,
    step_sign,
)


class TestParseRateNumber:
    def test_percent_string(self):
        assert parse_rate_number("5.50%") == 5.5

    def test_empty_none(self):
        assert parse_rate_number("") is None
        assert parse_rate_number(None) is None


class TestDirection:
    def test_hike(self):
        assert direction_from_actual_previous("5.75%", "5.50%") is PolicyRateDirection.HIKE

    def test_cut(self):
        assert direction_from_actual_previous("5.25%", "5.50%") is PolicyRateDirection.CUT

    def test_hold(self):
        assert direction_from_actual_previous("5.50%", "5.50%") is PolicyRateDirection.HOLD

    def test_unknown(self):
        assert direction_from_actual_previous("", "5.50%") is PolicyRateDirection.UNKNOWN


class TestStepSign:
    def test_signs(self):
        assert step_sign(PolicyRateDirection.HIKE) == 1
        assert step_sign(PolicyRateDirection.CUT) == -1
        assert step_sign(PolicyRateDirection.HOLD) == 0


class TestPolicyRateStepVO:
    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title"):
            PolicyRateStep(
                event_date=date(2026, 7, 1),
                title="",
                direction=PolicyRateDirection.HOLD,
            )
