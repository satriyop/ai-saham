"""Tests for open_30m labels generator."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.application.services.pre_open_observation_payload import PRE_OPEN_WORKFLOW
from src.application.use_case.generate_pre_open_open30m_labels_use_case import (
    generate_pre_open_open30m_labels,
)


def test_open30m_labels_from_saved_observations_and_tracks(tmp_path: Path):
    day = tmp_path / "20260618"
    day.mkdir()
    (day / "track_0900.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:00:00+07:00",
                "tickers": {
                    "BBCA": {
                        "opening_price": 10000,
                        "opening_price_confidence": "HIGH",
                    }
                },
            }
        )
    )
    (day / "track_0930.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:30:00+07:00",
                "tickers": {
                    "BBCA": {
                        "opening_price": 10050,
                        "opening_price_confidence": "HIGH",
                    }
                },
            }
        )
    )

    payload = {
        "workflow": PRE_OPEN_WORKFLOW,
        "screen_result": "pass",
        "candidate": {
            "ticker": "BBCA",
            "entry_range_low": "9900",
            "entry_range_high": "10100",
            "entry_price": "10050",
            "stop_loss_price": "9800",
        },
        "signal": {"score": 72, "strength": "STRONG", "entry_quality": "ENTER"},
        "trade_setup": {"action": "ENTER"},
    }
    row = SimpleNamespace(
        ticker="BBCA",
        workflow=PRE_OPEN_WORKFLOW,
        payload=payload,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
    )
    repo = SimpleNamespace(list_all_by_date=lambda d: [row])

    result = generate_pre_open_open30m_labels(
        date(2026, 6, 18),
        observations_repository=repo,
        opening_data_dir=tmp_path,
        persist=True,
    )

    assert result.decision_source == "saved_observations"
    assert result.labeled_count == 1
    assert result.labels[0].outcome == "SUCCESS"
    assert result.labels[0].participated is True
    assert result.labels[0].open_to_close_return_pct is not None
    assert result.output_path is not None
    assert Path(result.output_path).exists()


def test_open30m_labels_fail_closed_without_observations(tmp_path: Path):
    day = tmp_path / "20260618"
    day.mkdir()
    (day / "track_0900.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:00:00+07:00",
                "tickers": {"BBCA": {"opening_price": 10000}},
            }
        )
    )
    (day / "ops_session.json").write_text(
        json.dumps({"candidates": [{"ticker": "BBCA"}]})
    )
    repo = SimpleNamespace(list_all_by_date=lambda d: [])

    with pytest.raises(FileNotFoundError, match="research pre-open capture"):
        generate_pre_open_open30m_labels(
            date(2026, 6, 18),
            observations_repository=repo,
            opening_data_dir=tmp_path,
            persist=False,
        )
