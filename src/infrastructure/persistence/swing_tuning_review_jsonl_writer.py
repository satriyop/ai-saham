"""JSONL store for swing tuning review artifacts.

Layer: Infrastructure
"""

from __future__ import annotations

import json
from pathlib import Path

from src.domain.ports.swing_tuning_review_store import SwingTuningReviewStore


class SwingTuningReviewJsonlWriter(SwingTuningReviewStore):
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, record: dict) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return True

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        records: list[dict] = []
        with open(self._path) as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
        return records
