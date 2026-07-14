"""Data transfer objects for swing tuning review artifacts.

Layer: Application DTO
"""

from __future__ import annotations

from dataclasses import dataclass


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
    min_sample_size: int | None
    trade_count: int | None
    candidate_observation_count: int | None
    total_return_pct: float | None
    win_rate_pct: float | None
    tuning_diff_status: str | None
    proposed_count: int | None
    rejected_count: int | None
    is_ratio: float | None  # 0.0–1.0; None = not tracked; 1.0 = full-data (no OOS split)
    # True when is_end_date stored; patch validation also requires
    # oos_start_date and oos_backtest_summary
    walk_forward_enforced: bool
    oos_trade_count: int | None  # None when walk_forward not enforced
    oos_total_return_pct: float | None
    oos_win_rate_pct: float | None

    def to_dict(self) -> dict:
        return {
            "recorded_at": self.recorded_at,
            "setup": self.setup,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "sample_status": self.sample_status,
            "min_sample_size": self.min_sample_size,
            "trade_count": self.trade_count,
            "candidate_observation_count": self.candidate_observation_count,
            "total_return_pct": self.total_return_pct,
            "win_rate_pct": self.win_rate_pct,
            "tuning_diff_status": self.tuning_diff_status,
            "proposed_count": self.proposed_count,
            "rejected_count": self.rejected_count,
            "is_ratio": self.is_ratio,
            "walk_forward_enforced": self.walk_forward_enforced,
            "oos_trade_count": self.oos_trade_count,
            "oos_total_return_pct": self.oos_total_return_pct,
            "oos_win_rate_pct": self.oos_win_rate_pct,
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


@dataclass(frozen=True)
class SwingTuningAppliedPatchSummary:
    applied_at: str | None
    patch_path: str | None
    change_count: int
    target_paths: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "applied_at": self.applied_at,
            "patch_path": self.patch_path,
            "change_count": self.change_count,
            "target_paths": list(self.target_paths),
        }


@dataclass(frozen=True)
class SwingTuningPostApplyMeasurement:
    status: str
    applied_patch: SwingTuningAppliedPatchSummary | None
    baseline: SwingTuningReviewSummary | None
    candidate: SwingTuningReviewSummary | None
    metric_deltas: tuple[SwingTuningMetricDelta, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "applied_patch": (
                self.applied_patch.to_dict() if self.applied_patch else None
            ),
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "metric_deltas": [delta.to_dict() for delta in self.metric_deltas],
            "notes": list(self.notes),
        }
