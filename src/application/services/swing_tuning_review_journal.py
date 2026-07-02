"""Application service for persisted swing tuning review artifacts.

Intent:
    Store review-only swing tuning artifacts for later comparison. This service
    does not generate proposals, apply YAML changes, or call AI.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
