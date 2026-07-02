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


@dataclass(frozen=True)
class SwingTuningMetricDelta:
    name: str
    baseline_value: object | None
    candidate_value: object | None
    delta: float | int | None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "baseline_value": self.baseline_value,
            "candidate_value": self.candidate_value,
            "delta": self.delta,
        }


@dataclass(frozen=True)
class SwingTuningReviewComparison:
    status: str
    baseline: SwingTuningReviewSummary | None
    candidate: SwingTuningReviewSummary | None
    metric_deltas: tuple[SwingTuningMetricDelta, ...]
    newly_proposed_target_paths: tuple[str, ...]
    disappeared_target_paths: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "metric_deltas": [delta.to_dict() for delta in self.metric_deltas],
            "newly_proposed_target_paths": list(self.newly_proposed_target_paths),
            "disappeared_target_paths": list(self.disappeared_target_paths),
            "notes": list(self.notes),
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

    def compare_latest(self) -> SwingTuningReviewComparison:
        records = sorted(
            self._store.read_all(),
            key=lambda record: str(record.get("recorded_at") or ""),
            reverse=True,
        )
        if len(records) < 2:
            return SwingTuningReviewComparison(
                status="INSUFFICIENT_HISTORY",
                baseline=None,
                candidate=_summarize_record(records[0]) if records else None,
                metric_deltas=(),
                newly_proposed_target_paths=(),
                disappeared_target_paths=(),
                notes=("Need at least two saved tuning reviews to compare.",),
            )

        candidate_record = records[0]
        baseline_record = records[1]
        baseline = _summarize_record(baseline_record)
        candidate = _summarize_record(candidate_record)
        baseline_targets = _proposed_target_paths(baseline_record)
        candidate_targets = _proposed_target_paths(candidate_record)
        return SwingTuningReviewComparison(
            status="READY",
            baseline=baseline,
            candidate=candidate,
            metric_deltas=_metric_deltas(baseline, candidate),
            newly_proposed_target_paths=tuple(
                sorted(candidate_targets - baseline_targets)
            ),
            disappeared_target_paths=tuple(
                sorted(baseline_targets - candidate_targets)
            ),
            notes=(
                "Comparison is read-only and based on saved review artifacts.",
                "Latest saved run is candidate; previous saved run is baseline.",
            ),
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


def _metric_deltas(
    baseline: SwingTuningReviewSummary,
    candidate: SwingTuningReviewSummary,
) -> tuple[SwingTuningMetricDelta, ...]:
    specs = (
        ("trade_count", baseline.trade_count, candidate.trade_count),
        (
            "candidate_observation_count",
            baseline.candidate_observation_count,
            candidate.candidate_observation_count,
        ),
        ("total_return_pct", baseline.total_return_pct, candidate.total_return_pct),
        ("win_rate_pct", baseline.win_rate_pct, candidate.win_rate_pct),
        ("proposed_count", baseline.proposed_count, candidate.proposed_count),
        ("rejected_count", baseline.rejected_count, candidate.rejected_count),
    )
    return tuple(
        SwingTuningMetricDelta(
            name=name,
            baseline_value=baseline_value,
            candidate_value=candidate_value,
            delta=_delta(baseline_value, candidate_value),
        )
        for name, baseline_value, candidate_value in specs
    )


def _delta(
    baseline_value: int | float | None,
    candidate_value: int | float | None,
) -> int | float | None:
    if baseline_value is None or candidate_value is None:
        return None
    return candidate_value - baseline_value


def _proposed_target_paths(record: dict[str, Any]) -> set[str]:
    tuning_diff = _dict(record.get("tuning_config_diff"))
    paths: set[str] = set()
    for item in _list(tuning_diff.get("diff_items")):
        item_dict = _dict(item)
        if item_dict.get("proposed_value") is not None:
            target_path = _str(item_dict.get("target_path"))
            if target_path:
                paths.add(target_path)
    return paths


def _list(value: object) -> list:
    return value if isinstance(value, list) else []
