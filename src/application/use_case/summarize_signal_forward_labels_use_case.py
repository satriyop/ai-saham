"""Summarize persisted signal forward labels for attribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.domain.ports.signal_forward_labels_repository import (
    SignalForwardLabelsRepository,
)
from src.domain.value_objects.signal_artifact_schema import (
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
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
        all_labels = tuple(
            self._repository.list(
                signal_date=request.signal_date,
                horizon=request.horizon,
                ticker=request.ticker,
            )
        )
        # HIGH-2 Finding 4: canonical attribution only. Legacy schema labels
        # remain readable through the repository directly but must never
        # contaminate canonical buckets/counts/returns.
        labels = tuple(
            label
            for label in all_labels
            if label.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
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
            ("market_regime_at_signal", fp.market_regime_at_signal or "UNKNOWN"),
            ("regime_confidence_bucket", _score_bucket(fp.regime_confidence_at_signal)),
            ("regime_stability_at_signal", fp.regime_stability_at_signal or "UNKNOWN"),
            ("days_in_regime_bucket", _days_in_regime_bucket(fp.days_in_regime_at_signal)),
            (
                "regime_detection_method_at_signal",
                fp.regime_detection_method_at_signal or "UNKNOWN",
            ),
            ("strategy_name", fp.strategy_name or "UNKNOWN"),
            ("strategy_rule", fp.strategy_rule_name or "UNKNOWN"),
            ("strategy_outcome", fp.strategy_evidence_outcome or "UNKNOWN"),
            ("strategy_route", fp.strategy_evidence_route or "UNKNOWN"),
            (
                "ia_foreign_track_coverage",
                _score_bucket(fp.ia_foreign_track_coverage),
            ),
            (
                "ia_domestic_track_coverage",
                _score_bucket(fp.ia_domestic_track_coverage),
            ),
            (
                "ia_foreign_track_conviction",
                _score_bucket(fp.ia_foreign_track_conviction),
            ),
            (
                "ia_domestic_track_conviction",
                _score_bucket(fp.ia_domestic_track_conviction),
            ),
            ("ticker_profile_label", fp.ticker_profile_label or "UNKNOWN"),
            ("tp_market_cap_bucket", fp.tp_market_cap_bucket or "UNKNOWN"),
            ("tp_market_tier", fp.tp_market_tier or "UNKNOWN"),
            ("tp_coverage_score", _score_bucket(fp.tp_coverage_score)),
            ("alpha_bucket", _score_bucket_100(fp.alpha_score)),
            ("trigger_bucket", _score_bucket_100(fp.trigger_score)),
            (
                "alpha_trigger_final_bucket",
                _score_bucket_100(fp.alpha_trigger_final_exact_score),
            ),
            ("alpha_trigger_horizon", fp.alpha_trigger_horizon or "UNKNOWN"),
            (
                "flow_trigger_allowed",
                "UNKNOWN" if fp.flow_trigger_allowed is None else str(fp.flow_trigger_allowed),
            ),
            # HIGH-2 Finding 4: canonical production-authority coverage
            # replaces the removed legacy fingerprint fields below — no
            # fallback to those ambiguous generic fields is permitted here.
            (
                "signal_authority_coverage_bucket",
                _score_bucket(fp.signal_authority_coverage),
            ),
            ("setup_readiness_status", fp.setup_readiness_status or "UNKNOWN"),
            (
                "setup_readiness_current_phase",
                fp.setup_readiness_current_phase or "UNKNOWN",
            ),
            # Point 3: explicit dry-up/expansion volume trigger evidence.
            (
                "volume_dry_up_confirmed",
                "UNKNOWN" if fp.volume_dry_up_confirmed is None else str(fp.volume_dry_up_confirmed),
            ),
            (
                "volume_expansion_confirmed",
                "UNKNOWN" if fp.volume_expansion_confirmed is None else str(fp.volume_expansion_confirmed),
            ),
            (
                "volume_trigger_confirmed",
                "UNKNOWN" if fp.volume_trigger_confirmed is None else str(fp.volume_trigger_confirmed),
            ),
            ("sc_sector", fp.sc_sector or "UNKNOWN"),
            ("sc_sector_regime", fp.sc_sector_regime or "UNKNOWN"),
            # Phase G company_quality_context producer (DIAGNOSTIC): attribution
            # buckets over persisted cq_* fields. Missing → UNKNOWN, never crash.
            ("cq_valuation_score", _score_bucket_100(fp.cq_valuation_score)),
            ("cq_analyst_score", _score_bucket_100(fp.cq_analyst_score)),
            ("cq_insider_score", _score_bucket_100(fp.cq_insider_score)),
            ("cq_seasonality_score", _score_bucket_100(fp.cq_seasonality_score)),
            ("cq_aggregate_score", _score_bucket_100(fp.cq_aggregate_score)),
            ("cq_coverage_score", _score_bucket(fp.cq_coverage_score)),
            (
                "cq_present_axis_count",
                "UNKNOWN"
                if fp.cq_present_axis_count is None
                else str(fp.cq_present_axis_count),
            ),
            # Volatility context attribution: reads persisted fingerprint
            # values only — never recomputes ATR during attribution.
            ("volatility_bucket_at_signal", fp.volatility_bucket_at_signal or "UNKNOWN"),
            ("atr_pct_bucket", _atr_pct_bucket(fp.atr_pct_at_signal)),
            (
                "volatility_size_multiplier_bucket",
                _volatility_size_multiplier_bucket(fp.volatility_size_multiplier_at_signal),
            ),
        )
        for key in keys:
            groups.setdefault(key, []).append(label)

        # Membership groups: one label may have multiple missing/failed
        # requirements, so it is counted under each normalized value — group
        # totals may therefore exceed the overall label count.
        for value in _normalized_memberships(fp.setup_readiness_missing_required_inputs):
            groups.setdefault(("setup_readiness_missing_required_input", value), []).append(
                label
            )
        for value in _normalized_memberships(fp.setup_readiness_failed_requirements):
            groups.setdefault(("setup_readiness_failed_requirement", value), []).append(label)

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


def _normalized_memberships(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted({value.strip() for value in values if value.strip()}))
    return normalized or ("NONE",)


def _score_bucket(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 0.4:
        return "LOW"
    if value < 0.7:
        return "MEDIUM"
    return "HIGH"


def _score_bucket_100(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    return _score_bucket(float(value) / 100.0)


def _days_in_regime_bucket(value: int | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value <= 2:
        return "D0_2"
    if value <= 5:
        return "D3_5"
    if value <= 10:
        return "D6_10"
    return "D11_PLUS"


def _atr_pct_bucket(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 2.0:
        return "LT_2"
    if value < 5.0:
        return "D2_5"
    if value < 8.0:
        return "D5_8"
    return "GTE_8"


def _volatility_size_multiplier_bucket(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    return f"{value:.2f}"


def _average(values) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 4)
