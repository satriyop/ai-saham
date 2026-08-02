"""Active Stockbit calendar snapshot authority tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.trading_session_calendar_snapshot import (
    STOCKBIT_TRADING_SESSIONS_CONTRACT,
    TradingSessionCalendarSnapshot,
    validate_active_stockbit_calendar_snapshot,
    validate_trading_session_calendar_snapshot,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
SESSIONS = (date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3))


def _snap(**overrides) -> TradingSessionCalendarSnapshot:
    kwargs = dict(
        coverage_start=date(2026, 7, 1),
        coverage_end=date(2026, 7, 31),
        ordered_sessions=SESSIONS,
        source_revision="stockbit.test.v1",
        captured_at=NOW,
    )
    kwargs.update(overrides)
    return TradingSessionCalendarSnapshot.create(**kwargs)


def test_active_validator_accepts_stockbit_ihsg() -> None:
    snap = _snap()
    validate_active_stockbit_calendar_snapshot(snap)


def test_structural_validator_accepts_rehashed_yahoo_but_active_rejects() -> None:
    yahoo = _snap(source="yahoo")
    validate_trading_session_calendar_snapshot(yahoo)
    with pytest.raises(LearningContractError, match="source must be stockbit"):
        validate_active_stockbit_calendar_snapshot(yahoo)


def test_active_rejects_invented_contract() -> None:
    bad = _snap(contract_id="invented.contract.v1")
    validate_trading_session_calendar_snapshot(bad)
    with pytest.raises(LearningContractError, match="unsupported calendar contract"):
        validate_active_stockbit_calendar_snapshot(bad)


def test_active_rejects_bbca_benchmark() -> None:
    bad = _snap(benchmark="BBCA")
    validate_trading_session_calendar_snapshot(bad)
    with pytest.raises(LearningContractError, match="benchmark must be IHSG"):
        validate_active_stockbit_calendar_snapshot(bad)


def test_create_rejects_blank_source_revision() -> None:
    with pytest.raises(LearningContractError, match="source_revision"):
        _snap(source_revision="  ")


def test_contract_constant_is_stockbit_ihsg_history() -> None:
    assert STOCKBIT_TRADING_SESSIONS_CONTRACT == "stockbit.trading_sessions.ihsg_history.v1"


def test_source_revision_whitespace_rejected_on_create() -> None:
    with pytest.raises(LearningContractError, match="whitespace"):
        _snap(source_revision=" rev ")


def test_from_mapping_rejects_string_coercion_and_padding() -> None:
    snap = _snap()
    raw = snap.to_dict()
    raw["source_revision"] = " stockbit.test.v1 "
    with pytest.raises(LearningContractError):
        TradingSessionCalendarSnapshot.from_mapping(raw)
    raw2 = snap.to_dict()
    raw2["coverage_start"] = 20260701
    with pytest.raises(LearningContractError):
        TradingSessionCalendarSnapshot.from_mapping(raw2)
