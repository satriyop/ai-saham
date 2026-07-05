"""Summarize persisted signal forward labels for attribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.domain.ports.signal_forward_labels_repository import (
    SignalForwardLabelsRepository,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
)


@dataclass(frozen=True)
class SignalForwardLabelAttributionBucket:
    group: str
    key: str
    observation_count: int
    success_count: int
    failure_count: int
    neutral_count: int
    unavailable_count: int
    average_close_return: float | None
    average_max_forward_return: float | None
    average_max_adverse_excursion: float | None

    def to_dict(self) -> dict:
        return {
            "group": self.group,
            "key": self.key,
            "observation_count": self.observation_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "neutral_count": self.neutral_count,
            "unavailable_count": self.unavailable_count,
            "average_close_return": self.average_close_return,
            "average_max_forward_return": self.average_max_forward_return,
            "average_max_adverse_excursion": self.average_max_adverse_excursion,
        }


@dataclass(frozen=True)
class SummarizeSignalForwardLabelsRequest:
    signal_date: date | None = None
    horizon: SignalLabelHorizon | None = None
    ticker: str | None = None


@dataclass(frozen=True)
class SummarizeSignalForwardLabelsResponse:
    labels: tuple[SignalForwardLabel, ...] = field(default_factory=tuple)
    buckets: tuple[SignalForwardLabelAttributionBucket, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "label_count": len(self.labels),
            "buckets": [bucket.to_dict() for bucket in self.buckets],
        }


class SummarizeSignalForwardLabelsUseCase:
    """Build attribution views from persisted labels and fingerprints only."""

    def __init__(self, repository: SignalForwardLabelsRepository) -> None:
        self._repository = repository

    def execute(
        self,
        request: SummarizeSignalForwardLabelsRequest,
    ) -> SummarizeSignalForwardLabelsResponse:
        labels = tuple(
            self._repository.list(
                signal_date=request.signal_date,
                horizon=request.horizon,
                ticker=request.ticker,
            )
        )
        buckets = tuple(_build_buckets(labels))
        return SummarizeSignalForwardLabelsResponse(labels=labels, buckets=buckets)


def _build_buckets(
    labels: tuple[SignalForwardLabel, ...],
) -> list[SignalForwardLabelAttributionBucket]:
    groups: dict[tuple[str, str], list[SignalForwardLabel]] = {}
    for label in labels:
        fp = label.fingerprint
        keys = (
            ("setup_family", fp.setup_family or "UNKNOWN"),
            ("setup_phase", fp.setup_phase or "UNKNOWN"),
            (
                "phase_sequence_valid",
                "UNKNOWN" if fp.phase_sequence_valid is None else str(fp.phase_sequence_valid),
            ),
            ("market_regime", str(fp.market_regime.get("regime") or "UNKNOWN")),
            ("coverage_bucket", _score_bucket(fp.coverage)),
            ("conviction_bucket", _score_bucket(fp.conviction)),
        )
        for key in keys:
            groups.setdefault(key, []).append(label)

    return [
        _summarize(group, key, rows)
        for (group, key), rows in sorted(groups.items(), key=lambda item: item[0])
    ]


def _summarize(
    group: str,
    key: str,
    labels: list[SignalForwardLabel],
) -> SignalForwardLabelAttributionBucket:
    return SignalForwardLabelAttributionBucket(
        group=group,
        key=key,
        observation_count=len(labels),
        success_count=sum(
            1 for label in labels if label.outcome_label == SignalForwardOutcome.SUCCESS
        ),
        failure_count=sum(
            1 for label in labels if label.outcome_label == SignalForwardOutcome.FAILURE
        ),
        neutral_count=sum(
            1 for label in labels if label.outcome_label == SignalForwardOutcome.NEUTRAL
        ),
        unavailable_count=sum(
            1 for label in labels if label.outcome_label == SignalForwardOutcome.UNAVAILABLE
        ),
        average_close_return=_average(label.close_return for label in labels),
        average_max_forward_return=_average(label.max_forward_return for label in labels),
        average_max_adverse_excursion=_average(label.max_adverse_excursion for label in labels),
    )


def _score_bucket(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 0.4:
        return "LOW"
    if value < 0.7:
        return "MEDIUM"
    return "HIGH"


def _average(values) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 4)
