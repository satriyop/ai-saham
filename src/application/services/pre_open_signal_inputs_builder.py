"""Build typed pre-open inputs without evaluating signal policy.

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.application.dto.pre_open_signal import PreOpenSignalEvaluationInput
from src.application.services.pre_open_signal_evidence_builder import (
    build_pre_open_signal_evidence,
)
from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
)


class PreOpenSignalInputsBuilder:
    """Translate a screened candidate into the canonical SignalEngine input."""

    def __init__(self, config: PreOpenDirectionalBaselineConfig | None = None) -> None:
        self._config = config or PreOpenDirectionalBaselineConfig()

    @property
    def config(self) -> PreOpenDirectionalBaselineConfig:
        return self._config

    def build(
        self,
        candidate: Any,
        *,
        trade_date: date,
        collection_started_at: datetime | None = None,
        decision_at: datetime | None = None,
        capture_phase: str = "UNKNOWN",
        source_is_live: bool = False,
        snapshot_ref: str | None = None,
        delta_iev: int | None = None,
    ) -> PreOpenSignalEvaluationInput:
        ticker = str(getattr(candidate, "ticker", "") or "")
        return PreOpenSignalEvaluationInput(
            ticker=ticker,
            snapshot_date=trade_date,
            evidence=build_pre_open_signal_evidence(
                candidate,
                trade_date=trade_date,
                collection_started_at=collection_started_at,
                decision_at=decision_at,
                capture_phase=capture_phase,
                source_is_live=source_is_live,
                snapshot_ref=snapshot_ref,
                config=self._config,
                delta_iev=delta_iev,
            ),
        )
