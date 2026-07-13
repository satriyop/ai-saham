"""Tests for pre-open sidecar artifact writer."""

import json
from datetime import date
from decimal import Decimal

from src.adapters.cli.pre_open_sidecar_writer import write_pre_open_sidecar
from src.domain.value_objects.screener_result import ScreenerCandidate


def _candidate(ticker: str) -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        iev=150000,
        entry_price=Decimal("1000"),
        stop_loss_price=Decimal("950"),
        capital=Decimal("3000000"),
    )


def test_sidecar_schema_keys_are_preserved(tmp_path):
    sidecar_path = tmp_path / "pre-open.json"

    write_pre_open_sidecar(
        candidates=[_candidate("BBCA")],
        screened_date=date(2026, 6, 12),
        sidecar_path=sidecar_path,
    )

    data = json.loads(sidecar_path.read_text())
    assert set(data.keys()) == {
        "schema_version",
        "artifact_type",
        "screened_at",
        "market_regime",
        "candidates",
    }
    assert data["schema_version"] == 1
    assert data["artifact_type"] == "pre_open_session"
    assert data["screened_at"] == "2026-06-12"

    candidate_keys = set(data["candidates"][0].keys())
    assert candidate_keys == {
        "ticker",
        "iev",
        "gap_pct",
        "entry_range_low",
        "entry_range_high",
        "suggested_entry",
        "atr_stop",
        "trend",
        "rsi",
        "opening_broker_backing_tag",
        "opening_broker_backing_score",
        "opening_broker_buy_streak",
        "foreign_vwap",
        "fvwap_discount_pct",
        "prev_high",
        "prev_low",
        "ticker_notation",
    }


def test_sidecar_serializes_decimal_and_date_fields_as_strings(tmp_path):
    sidecar_path = tmp_path / "pre-open.json"

    write_pre_open_sidecar(
        candidates=[_candidate("BBCA")],
        screened_date=date(2026, 6, 12),
        sidecar_path=sidecar_path,
    )

    data = json.loads(sidecar_path.read_text())
    candidate = data["candidates"][0]
    assert candidate["ticker"] == "BBCA"
    assert candidate["iev"] == 150000
    assert candidate["suggested_entry"] == "1000"
    assert candidate["atr_stop"] == "950"
    assert candidate["gap_pct"] is None


def test_sidecar_market_regime_none_writes_null(tmp_path):
    sidecar_path = tmp_path / "pre-open.json"

    write_pre_open_sidecar(
        candidates=[_candidate("BBCA")],
        screened_date=date(2026, 6, 12),
        sidecar_path=sidecar_path,
        market_regime=None,
    )

    data = json.loads(sidecar_path.read_text())
    assert data["market_regime"] is None


def test_sidecar_creates_parent_directory(tmp_path):
    sidecar_path = tmp_path / "nested" / "dir" / "pre-open.json"

    write_pre_open_sidecar(
        candidates=[_candidate("BBCA")],
        screened_date=date(2026, 6, 12),
        sidecar_path=sidecar_path,
    )

    assert sidecar_path.exists()
