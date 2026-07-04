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
    min_sample_size: int | None
    trade_count: int | None
    candidate_observation_count: int | None
    total_return_pct: float | None
    win_rate_pct: float | None
    tuning_diff_status: str | None
    proposed_count: int | None
    rejected_count: int | None
    is_ratio: float | None  # 0.0–1.0; None = not tracked; 1.0 = full-data (no OOS split)
    walk_forward_enforced: bool  # True when is_end_date stored; patch validation also requires oos_start_date and oos_backtest_summary
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
        notes_list = [
            "Comparison is read-only and based on saved review artifacts.",
            "Latest saved run is candidate; previous saved run is baseline.",
        ]
        if candidate.is_ratio is None or candidate.is_ratio >= 1.0:
            notes_list.append(
                "walk_forward_not_enforced: candidate review used full data "
                "(no OOS split). Run with --is-ratio 0.70 to enforce 70/30 "
                "IS/OOS split."
            )
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
            notes=tuple(notes_list),
        )

    def measure_latest_apply(
        self,
        apply_records: list[dict],
    ) -> SwingTuningPostApplyMeasurement:
        latest_apply = _latest_apply_record(apply_records)
        if latest_apply is None:
            return SwingTuningPostApplyMeasurement(
                status="NO_APPLY_LOG",
                applied_patch=None,
                baseline=None,
                candidate=None,
                metric_deltas=(),
                notes=("No swing_tuning_patch_apply records were found.",),
            )

        applied_patch = _summarize_apply_record(latest_apply)
        applied_at = applied_patch.applied_at
        if applied_at is None:
            return SwingTuningPostApplyMeasurement(
                status="APPLY_LOG_INVALID",
                applied_patch=applied_patch,
                baseline=None,
                candidate=None,
                metric_deltas=(),
                notes=("Latest apply log record has no applied_at timestamp.",),
            )

        review_records = sorted(
            self._store.read_all(),
            key=lambda record: str(record.get("recorded_at") or ""),
        )
        baseline_record = _latest_review_before(review_records, applied_at)
        candidate_record = _latest_review_after(review_records, applied_at)
        baseline = _summarize_record(baseline_record) if baseline_record else None
        candidate = _summarize_record(candidate_record) if candidate_record else None
        if baseline is None or candidate is None:
            return SwingTuningPostApplyMeasurement(
                status="INSUFFICIENT_REVIEW_HISTORY",
                applied_patch=applied_patch,
                baseline=baseline,
                candidate=candidate,
                metric_deltas=(),
                notes=(
                    "Need one saved tuning review before and one after the latest apply.",
                    "Run `saham trade tune-swing --save` after applying a patch.",
                ),
            )

        return SwingTuningPostApplyMeasurement(
            status="READY",
            applied_patch=applied_patch,
            baseline=baseline,
            candidate=candidate,
            metric_deltas=_metric_deltas(baseline, candidate),
            notes=(
                "Measurement is deterministic and based on saved review artifacts.",
                "This is before/after attribution, not proof of causality.",
            ),
        )


def _summarize_record(record: dict[str, Any]) -> SwingTuningReviewSummary:
    sample = _dict(record.get("sample"))
    backtest = _dict(record.get("backtest_summary"))
    tuning_diff = _dict(record.get("tuning_config_diff"))
    tuning_diff_summary = _dict(tuning_diff.get("summary"))
    is_ratio_raw = _float(record.get("is_ratio"))
    # walk_forward_enforced is True only when the backtest was actually run on the
    # IS window — signalled by is_end_date being present in the record. Storing
    # is_ratio alone does not constitute enforcement; it's metadata.
    walk_forward_enforced = _str(record.get("is_end_date")) is not None
    oos = _dict(record.get("oos_backtest_summary"))
    return SwingTuningReviewSummary(
        recorded_at=_str(record.get("recorded_at")),
        setup=_str(record.get("setup")),
        start_date=_str(record.get("start_date")),
        end_date=_str(record.get("end_date")),
        sample_status=_str(sample.get("status")),
        min_sample_size=_int(sample.get("min_sample_size")),
        trade_count=_int(backtest.get("trade_count")),
        candidate_observation_count=_int(
            backtest.get("candidate_observation_count")
        ),
        total_return_pct=_float(backtest.get("total_return_pct")),
        win_rate_pct=_float(backtest.get("win_rate_pct")),
        tuning_diff_status=_str(tuning_diff.get("status")),
        proposed_count=_int(tuning_diff_summary.get("proposed_count")),
        rejected_count=_int(tuning_diff_summary.get("rejected_count")),
        is_ratio=is_ratio_raw,
        walk_forward_enforced=walk_forward_enforced,
        oos_trade_count=_int(oos.get("trade_count")),
        oos_total_return_pct=_float(oos.get("total_return_pct")),
        oos_win_rate_pct=_float(oos.get("win_rate_pct")),
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
        ("is_ratio", baseline.is_ratio, candidate.is_ratio),
        ("oos_trade_count", baseline.oos_trade_count, candidate.oos_trade_count),
        ("oos_total_return_pct", baseline.oos_total_return_pct, candidate.oos_total_return_pct),
        ("oos_win_rate_pct", baseline.oos_win_rate_pct, candidate.oos_win_rate_pct),
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


def _latest_apply_record(records: list[dict]) -> dict[str, Any] | None:
    apply_records = [
        record
        for record in records
        if record.get("artifact_type") == "swing_tuning_patch_apply"
    ]
    if not apply_records:
        return None
    return max(
        apply_records,
        key=lambda record: str(record.get("applied_at") or ""),
    )


def _summarize_apply_record(record: dict[str, Any]) -> SwingTuningAppliedPatchSummary:
    changes = tuple(_dict(change) for change in _list(record.get("changes")))
    target_paths = tuple(
        sorted(
            target_path
            for target_path in (_str(change.get("target_path")) for change in changes)
            if target_path
        )
    )
    return SwingTuningAppliedPatchSummary(
        applied_at=_str(record.get("applied_at")),
        patch_path=_str(record.get("patch_path")),
        change_count=len(changes),
        target_paths=target_paths,
    )


def _latest_review_before(
    records: list[dict[str, Any]],
    timestamp: str,
) -> dict[str, Any] | None:
    before = [
        record
        for record in records
        if str(record.get("recorded_at") or "") < timestamp
    ]
    return before[-1] if before else None


def _latest_review_after(
    records: list[dict[str, Any]],
    timestamp: str,
) -> dict[str, Any] | None:
    after = [
        record
        for record in records
        if str(record.get("recorded_at") or "") > timestamp
    ]
    return after[0] if after else None


def _list(value: object) -> list:
    return value if isinstance(value, list) else []
