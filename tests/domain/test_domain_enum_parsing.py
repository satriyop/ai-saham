"""Tests for canonical domain enum values and legacy parsing."""

import pytest

from src.domain.indicators.indicator_reading import IndicatorReading
from src.domain.ports.csv_broker_parser import CsvFormat, ErrorStrategy
from src.domain.value_objects.risk_signal import RiskLevel
from src.domain.value_objects.trade_action import TradeAction


def test_risk_level_values_are_uppercase() -> None:
    assert RiskLevel.HIGH_RISK.value == "HIGH_RISK"
    assert RiskLevel.MODERATE.value == "MODERATE"
    assert RiskLevel.LOW_RISK.value == "LOW_RISK"


def test_risk_level_parse_accepts_legacy_values() -> None:
    assert RiskLevel.parse("HIGH_RISK") == RiskLevel.HIGH_RISK
    assert RiskLevel.parse("high_risk") == RiskLevel.HIGH_RISK
    assert RiskLevel.parse("low-risk") == RiskLevel.LOW_RISK


def test_indicator_reading_values_are_uppercase() -> None:
    assert IndicatorReading.BEARISH.value == "BEARISH"
    assert IndicatorReading.NEUTRAL.value == "NEUTRAL"
    assert IndicatorReading.BULLISH.value == "BULLISH"


def test_indicator_reading_parse_accepts_legacy_values() -> None:
    assert IndicatorReading.parse("BEARISH") == IndicatorReading.BEARISH
    assert IndicatorReading.parse("bearish") == IndicatorReading.BEARISH
    assert IndicatorReading.parse("bullish") == IndicatorReading.BULLISH


def test_trade_action_values_are_uppercase() -> None:
    assert TradeAction.ENTER_LONG.value == "ENTER_LONG"
    assert TradeAction.EXIT_LONG.value == "EXIT_LONG"
    assert TradeAction.HOLD.value == "HOLD"
    assert TradeAction.FLAT.value == "FLAT"


def test_trade_action_from_string_accepts_legacy_values() -> None:
    assert TradeAction.from_string("ENTER_LONG") == TradeAction.ENTER_LONG
    assert TradeAction.from_string("enter_long") == TradeAction.ENTER_LONG
    assert TradeAction.from_string("exit-long") == TradeAction.EXIT_LONG


def test_trade_action_from_string_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="Invalid action"):
        TradeAction.from_string("BUY")


def test_csv_format_values_are_uppercase() -> None:
    assert CsvFormat.SIMPLE.value == "SIMPLE"
    assert CsvFormat.DETAILED.value == "DETAILED"
    assert CsvFormat.CUSTOM.value == "CUSTOM"


def test_csv_format_parse_accepts_legacy_values() -> None:
    assert CsvFormat.parse("simple") == CsvFormat.SIMPLE
    assert CsvFormat.parse("DETAILED") == CsvFormat.DETAILED
    assert CsvFormat.parse("custom") == CsvFormat.CUSTOM


def test_error_strategy_values_are_uppercase() -> None:
    assert ErrorStrategy.SKIP.value == "SKIP"
    assert ErrorStrategy.FAIL.value == "FAIL"
    assert ErrorStrategy.REPORT.value == "REPORT"


def test_error_strategy_parse_accepts_legacy_values() -> None:
    assert ErrorStrategy.parse("skip") == ErrorStrategy.SKIP
    assert ErrorStrategy.parse("FAIL") == ErrorStrategy.FAIL
    assert ErrorStrategy.parse("report") == ErrorStrategy.REPORT
