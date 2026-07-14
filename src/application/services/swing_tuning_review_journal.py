"""Application service for persisted swing tuning review artifacts.

Intent:
    Store review-only swing tuning artifacts for later comparison. This service
    does not generate proposals, apply YAML changes, or call AI.

Layer: Application
"""

from __future__ import annotations

from datetime import datetime

from src.application.dto.swing_tuning_review import (
    SwingTuningPostApplyMeasurement,
    SwingTuningReviewComparison,
    SwingTuningReviewReport,
    SwingTuningReviewSaveResult,
)
from src.application.services.swing_tuning_post_apply_measurement import (
    measure_post_apply,
)
from src.application.services.swing_tuning_review_comparison import (
    compare_latest_review,
)
from src.application.services.swing_tuning_review_summary import (
    summarize_review_record,
)
from src.domain.ports.swing_tuning_review_store import SwingTuningReviewStore


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
            summarize_review_record(record)
            for record in sorted_records[:max(limit, 0)]
        )
        return SwingTuningReviewReport(total_records=len(records), records=summaries)

    def compare_latest(self) -> SwingTuningReviewComparison:
        sorted_records = sorted(
            self._store.read_all(),
            key=lambda record: str(record.get("recorded_at") or ""),
            reverse=True,
        )
        return compare_latest_review(sorted_records)

    def measure_latest_apply(self, apply_records: list[dict]) -> SwingTuningPostApplyMeasurement:
        review_records = sorted(
            self._store.read_all(),
            key=lambda record: str(record.get("recorded_at") or ""),
        )
        return measure_post_apply(apply_records, review_records)
