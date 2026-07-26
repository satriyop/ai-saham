"""Typed application boundary for canonical pre-open signal evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.dto.assess_signal import AssessSignalResponse
from src.domain.value_objects.pre_open_directional_baseline import (
    PreOpenBaselineAssessment,
)
from src.domain.value_objects.pre_open_signal_evidence import (
    PreOpenSignalEvidenceBundle,
)


@dataclass(frozen=True)
class PreOpenSignalEvaluationInput:
    ticker: str
    snapshot_date: date
    evidence: PreOpenSignalEvidenceBundle


@dataclass(frozen=True)
class PreOpenSignalEvaluationResult:
    response: AssessSignalResponse
    baseline: PreOpenBaselineAssessment
