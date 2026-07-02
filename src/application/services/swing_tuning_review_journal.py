"""Application service for persisted swing tuning review artifacts.

Intent:
    Store review-only swing tuning artifacts for later comparison. This service
    does not generate proposals, apply YAML changes, or call AI.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.domain.ports.swing_tuning_review_store import SwingTuningReviewStore


@dataclass(frozen=True)
class SwingTuningReviewSaveResult:
    saved: bool
    record_count: int
    recorded_at: str

    def to_dict(self) -> dict:
        return {
            "saved": self.saved,
            "record_count": self.record_count,
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True)
class SwingTuningReviewSummary:
    recorded_at: str | None
    setup: str | None
    start_date: str | None
    end_date: str | None
    sample_status: str | None
    trade_count: int | None
    candidate_observation_count: int | None
    total_return_pct: float | None
    win_rate_pct: float | None
    tuning_diff_status: str | None
    proposed_count: int | None
    rejected_count: int | None

    def to_dict(self) -> dict:
        return {
            "recorded_at": self.recorded_at,
            "setup": self.setup,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "sample_status": self.sample_status,
            "trade_count": self.trade_count,
            "candidate_observation_count": self.candidate_observation_count,
            "total_return_pct": self.total_return_pct,
            "win_rate_pct": self.win_rate_pct,
            "tuning_diff_status": self.tuning_diff_status,
            "proposed_count": self.proposed_count,
            "rejected_count": self.rejected_count,
        }


@dataclass(frozen=True)
class SwingTuningReviewReport:
    total_records: int
    records: tuple[SwingTuningReviewSummary, ...]

    def to_dict(self) -> dict:
        return {
            "total_records": self.total_records,
            "records": [record.to_dict() for record in self.records],
        }


class SwingTuningReviewJournal:
    def __init__(self, store: SwingTuningReviewStore) -> None:
        self._store = store

    def append_review(self, review: dict) -> SwingTuningReviewSaveResult:
        recorded_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
        record = {
            "recorded_at": recorded_at,
            **review,
        }
        saved = self._store.append(record)
        return SwingTuningReviewSaveResult(
            saved=saved,
            record_count=len(self._store.read_all()),
            recorded_at=recorded_at,
        )

    def review(self, limit: int = 10) -> SwingTuningReviewReport:
        records = self._store.read_all()
        sorted_records = sorted(
            records,
            key=lambda record: str(record.get("recorded_at") or ""),
            reverse=True,
        )
        summaries = tuple(
            _summarize_record(record)
            for record in sorted_records[:max(limit, 0)]
        )
        return SwingTuningReviewReport(
            total_records=len(records),
            records=summaries,
        )


def _summarize_record(record: dict[str, Any]) -> SwingTuningReviewSummary:
    sample = _dict(record.get("sample"))
    backtest = _dict(record.get("backtest_summary"))
    tuning_diff = _dict(record.get("tuning_config_diff"))
    tuning_diff_summary = _dict(tuning_diff.get("summary"))
    return SwingTuningReviewSummary(
        recorded_at=_str(record.get("recorded_at")),
        setup=_str(record.get("setup")),
        start_date=_str(record.get("start_date")),
        end_date=_str(record.get("end_date")),
        sample_status=_str(sample.get("status")),
        trade_count=_int(backtest.get("trade_count")),
        candidate_observation_count=_int(
            backtest.get("candidate_observation_count")
        ),
        total_return_pct=_float(backtest.get("total_return_pct")),
        win_rate_pct=_float(backtest.get("win_rate_pct")),
        tuning_diff_status=_str(tuning_diff.get("status")),
        proposed_count=_int(tuning_diff_summary.get("proposed_count")),
        rejected_count=_int(tuning_diff_summary.get("rejected_count")),
    )


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _str(value: object) -> str | None:
    return str(value) if value is not None else None


def _int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
