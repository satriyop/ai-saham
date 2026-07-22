"""Read-only readiness report for Phase I signal calibration (DQ-006 lean).

Reports valid, independent, same-cohort labeled samples with a visible
exclusion ledger. Ephemeral 70/30 OOS is diagnostic-only —
``promotion_eligible`` is always false.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from math import isinf

from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
    CandidateObservationsRepository,
)
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
    SignalObservationFingerprint,
)

_DIAGNOSTIC_MIN_OOS_LABELS = 10
_PATCH_MIN_IS_LABELS = 60
_PATCH_MIN_OOS_LABELS = 30
_PATCH_MIN_OOS_PROFIT_FACTOR = 1.15
_PATCH_MIN_OOS_AVERAGE_RETURN = 0.0
_OOS_FRACTION = 0.30
_OOS_SPLIT_MODE = "EPHEMERAL_CHRONOLOGICAL_70_30"

_ACCUMULATION_SETUP_FAMILIES = frozenset({"accumulation", "foreign_bounce"})


@dataclass(frozen=True)
class SignalReadinessTarget:
    raw: str
    profile: str
    setup_family: str
    market_cap_bucket: str | None
    horizon: SignalLabelHorizon
    is_diagnostic: bool = False

    @classmethod
    def parse(cls, raw: str) -> "SignalReadinessTarget":
        normalized = raw.strip()
        suffixes = tuple(f"_{horizon.value}" for horizon in SignalLabelHorizon)
        matched_horizon: SignalLabelHorizon | None = None
        base = normalized
        for horizon in SignalLabelHorizon:
            suffix = f"_{horizon.value}"
            if normalized.endswith(suffix):
                matched_horizon = horizon
                base = normalized[: -len(suffix)]
                break
        if matched_horizon is None:
            valid = ", ".join(s[1:] for s in suffixes)
            raise ValueError(f"target must end with one of: {valid}")

        parts = base.split("_")

        # Canonical target: ends with <bucket>_cap (e.g. large_cap).
        if len(parts) >= 5 and parts[-1] == "cap":
            market_cap_bucket = parts[-2]
            setup_family = parts[-3]
            profile = "_".join(parts[:-3])
            if not profile or not setup_family or not market_cap_bucket:
                raise ValueError(
                    "target profile, setup family, and market-cap bucket cannot be empty"
                )
            return cls(
                raw=normalized,
                profile=profile,
                setup_family=setup_family,
                market_cap_bucket=market_cap_bucket,
                horizon=matched_horizon,
                is_diagnostic=False,
            )

        # Diagnostic target: no market-cap bucket.
        if len(parts) >= 3:
            setup_family = parts[-1]
            profile = "_".join(parts[:-1])
            if not profile or not setup_family:
                raise ValueError("diagnostic target profile and setup family cannot be empty")
            return cls(
                raw=normalized,
                profile=profile,
                setup_family=setup_family,
                market_cap_bucket=None,
                horizon=matched_horizon,
                is_diagnostic=True,
            )

        raise ValueError(
            "target must include profile, setup family, and optionally a market-cap bucket"
        )


@dataclass(frozen=True)
class SignalReadinessExclusionLedger:
    excluded_schema_mismatch: int = 0
    excluded_unavailable: int = 0
    excluded_target_mismatch: int = 0
    excluded_wrong_cohort: int = 0
    excluded_unlinked_observation: int = 0
    excluded_duplicate_collapsed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "excluded_schema_mismatch": self.excluded_schema_mismatch,
            "excluded_unavailable": self.excluded_unavailable,
            "excluded_target_mismatch": self.excluded_target_mismatch,
            "excluded_wrong_cohort": self.excluded_wrong_cohort,
            "excluded_unlinked_observation": self.excluded_unlinked_observation,
            "excluded_duplicate_collapsed": self.excluded_duplicate_collapsed,
        }


@dataclass(frozen=True)
class SignalReadinessReport:
    target: SignalReadinessTarget
    observation_dates: tuple[date, ...]
    latest_observation_date: date | None
    latest_observation_count: int
    raw_latest_observation_count: int
    target_filter_count: int
    raw_target_filter_count: int
    label_count: int
    unavailable_label_count: int
    target_label_count: int
    raw_labeled_target_count: int
    labeled_target_count: int
    is_count: int
    oos_count: int
    oos_profit_factor: float | None
    oos_average_return: float | None
    diagnostic_ready: bool
    patch_eligible: bool
    promotion_eligible: bool
    oos_split: str
    selected_semantic_compatibility_id: str | None
    available_semantic_compatibility_ids: tuple[str, ...]
    unique_tickers: int
    unique_signal_dates: int
    exclusions: SignalReadinessExclusionLedger
    notes: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "target": self.target.raw,
            "is_diagnostic_target": self.target.is_diagnostic,
            "target_components": {
                "profile": self.target.profile,
                "setup_family": self.target.setup_family,
                "market_cap_bucket": self.target.market_cap_bucket,
                "horizon": self.target.horizon.value,
            },
            "observation_dates": [day.isoformat() for day in self.observation_dates],
            "latest_observation_date": (
                self.latest_observation_date.isoformat()
                if self.latest_observation_date
                else None
            ),
            "latest_per_ticker_observation_count": self.latest_observation_count,
            "raw_latest_observation_count": self.raw_latest_observation_count,
            "target_filter_count": self.target_filter_count,
            "raw_target_filter_count": self.raw_target_filter_count,
            "label_count": self.label_count,
            "unavailable_label_count": self.unavailable_label_count,
            "target_label_count": self.target_label_count,
            "raw_labeled_target_count": self.raw_labeled_target_count,
            "labeled_target_count": self.labeled_target_count,
            "unique_tickers": self.unique_tickers,
            "unique_signal_dates": self.unique_signal_dates,
            "exclusions": self.exclusions.to_dict(),
            "selected_semantic_compatibility_id": self.selected_semantic_compatibility_id,
            "available_semantic_compatibility_ids": list(
                self.available_semantic_compatibility_ids
            ),
            "is_oos": {
                "oos_split": self.oos_split,
                "is_count": self.is_count,
                "oos_count": self.oos_count,
                "diagnostic_ready": self.diagnostic_ready,
                "patch_eligible": self.patch_eligible,
                "calibration_floors_passed": self.patch_eligible,
                "promotion_eligible": self.promotion_eligible,
                "oos_profit_factor": (
                    "Infinity"
                    if self.oos_profit_factor is not None
                    and isinf(self.oos_profit_factor)
                    else self.oos_profit_factor
                ),
                "oos_average_return": self.oos_average_return,
            },
            "notes": list(self.notes),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class ReportSignalReadinessRequest:
    target: str
    semantic_compatibility_id: str | None = None


class ReportSignalReadinessUseCase:
    """Build a deterministic readiness report from persisted observations and labels."""

    def __init__(
        self,
        *,
        candidate_observations_repository: CandidateObservationsRepository,
        signal_forward_labels_repository: SignalForwardLabelsRepository,
    ) -> None:
        self._observations = candidate_observations_repository
        self._labels = signal_forward_labels_repository

    def execute(self, request: ReportSignalReadinessRequest) -> SignalReadinessReport:
        target = SignalReadinessTarget.parse(request.target)
        observation_dates = tuple(self._observations.list_canonical_snapshot_dates())
        latest_date = observation_dates[-1] if observation_dates else None
        latest_observations = (
            self._observations.list_latest_canonical_by_date(latest_date)
            if latest_date is not None
            else []
        )
        raw_latest_observations = (
            self._observations.list_canonical_by_date(latest_date)
            if latest_date is not None
            else []
        )
        latest_target_observations = [
            observation
            for observation in latest_observations
            if _observation_matches_target(observation, target)
        ]
        raw_latest_target_observations = [
            observation
            for observation in raw_latest_observations
            if _observation_matches_target(observation, target)
        ]

        all_canonical = _load_all_canonical_observations(
            self._observations, observation_dates
        )
        observation_index = _observation_link_index(all_canonical)
        available_cohorts = tuple(
            sorted(
                {
                    str(obs.semantic_compatibility_id)
                    for obs in all_canonical
                    if obs.semantic_compatibility_id is not None
                }
            )
        )
        selected_cohort, cohort_blocker = _resolve_cohort(
            available_cohorts=available_cohorts,
            requested=request.semantic_compatibility_id,
        )

        all_horizon_labels = tuple(self._labels.list(horizon=target.horizon))
        excluded_schema = sum(
            1
            for label in all_horizon_labels
            if label.schema_version != SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
        )
        current_schema_labels = tuple(
            label
            for label in all_horizon_labels
            if label.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
        )

        excluded_unlinked = 0
        excluded_wrong_cohort = 0
        excluded_unavailable = 0
        excluded_target_mismatch = 0
        raw_labeled_targets: list[SignalForwardLabel] = []

        if selected_cohort is None:
            # Fail closed: do not pool labels into IS/OOS when cohort is unresolved.
            for label in current_schema_labels:
                if label.outcome_label is SignalForwardOutcome.UNAVAILABLE:
                    excluded_unavailable += 1
                elif not _label_matches_target(label, target):
                    excluded_target_mismatch += 1
                else:
                    # Would-be targets are withheld due to cohort gate.
                    excluded_wrong_cohort += 1
        else:
            for label in current_schema_labels:
                link_key = _label_link_key(label)
                if link_key is None:
                    excluded_unlinked += 1
                    continue
                obs_cohort = observation_index.get(link_key)
                if obs_cohort is None:
                    excluded_unlinked += 1
                    continue
                if obs_cohort != selected_cohort:
                    excluded_wrong_cohort += 1
                    continue
                if label.outcome_label is SignalForwardOutcome.UNAVAILABLE:
                    excluded_unavailable += 1
                    continue
                if not _label_matches_target(label, target):
                    excluded_target_mismatch += 1
                    continue
                raw_labeled_targets.append(label)

        independent_labeled, collapsed = _collapse_independent_labeled_targets(
            tuple(raw_labeled_targets)
        )
        # Fingerprint-matching current-schema labels (diagnostic), independent of
        # IS/OOS eligibility. Cohort-unresolved still reports fingerprint matches.
        if selected_cohort is None:
            target_label_count = sum(
                1 for label in current_schema_labels if _label_matches_target(label, target)
            )
        else:
            target_label_count = 0
            for label in current_schema_labels:
                if not _label_matches_target(label, target):
                    continue
                link_key = _label_link_key(label)
                if link_key is None:
                    continue
                if observation_index.get(link_key) == selected_cohort:
                    target_label_count += 1

        is_rows, oos_rows = _split_is_oos(independent_labeled)
        oos_profit_factor = _profit_factor(oos_rows)
        oos_average_return = _average_return(oos_rows)
        blockers = _blockers(
            observation_dates=observation_dates,
            target_filter_count=len(latest_target_observations),
            label_count=len(current_schema_labels),
            labeled_target_count=len(independent_labeled),
            is_count=len(is_rows),
            oos_count=len(oos_rows),
            oos_profit_factor=oos_profit_factor,
            oos_average_return=oos_average_return,
            oos_rows=oos_rows,
            cohort_blocker=cohort_blocker,
        )
        diagnostic_ready = (
            selected_cohort is not None
            and len(oos_rows) >= _DIAGNOSTIC_MIN_OOS_LABELS
        )
        # Phase-I calibration floors only — never production/promotion authority.
        patch_eligible = (
            not blockers and not target.is_diagnostic and selected_cohort is not None
        )
        exclusions = SignalReadinessExclusionLedger(
            excluded_schema_mismatch=excluded_schema,
            excluded_unavailable=excluded_unavailable,
            excluded_target_mismatch=excluded_target_mismatch,
            excluded_wrong_cohort=excluded_wrong_cohort,
            excluded_unlinked_observation=excluded_unlinked,
            excluded_duplicate_collapsed=collapsed,
        )
        notes = _notes(
            latest_observation_count=len(latest_observations),
            raw_latest_observation_count=len(raw_latest_observations),
            is_diagnostic=target.is_diagnostic,
            collapsed_duplicates=collapsed,
            selected_cohort=selected_cohort,
        )
        unique_tickers = len({label.ticker.upper() for label in independent_labeled})
        unique_signal_dates = len({label.signal_date for label in independent_labeled})
        return SignalReadinessReport(
            target=target,
            observation_dates=observation_dates,
            latest_observation_date=latest_date,
            latest_observation_count=len(latest_observations),
            raw_latest_observation_count=len(raw_latest_observations),
            target_filter_count=len(latest_target_observations),
            raw_target_filter_count=len(raw_latest_target_observations),
            label_count=len(current_schema_labels),
            unavailable_label_count=excluded_unavailable,
            target_label_count=target_label_count,
            raw_labeled_target_count=len(raw_labeled_targets),
            labeled_target_count=len(independent_labeled),
            is_count=len(is_rows),
            oos_count=len(oos_rows),
            oos_profit_factor=oos_profit_factor,
            oos_average_return=oos_average_return,
            diagnostic_ready=diagnostic_ready,
            patch_eligible=patch_eligible,
            promotion_eligible=False,
            oos_split=_OOS_SPLIT_MODE,
            selected_semantic_compatibility_id=selected_cohort,
            available_semantic_compatibility_ids=available_cohorts,
            unique_tickers=unique_tickers,
            unique_signal_dates=unique_signal_dates,
            exclusions=exclusions,
            notes=tuple(notes),
            blockers=tuple(blockers),
        )


def _load_all_canonical_observations(
    repo: CandidateObservationsRepository,
    observation_dates: tuple[date, ...],
) -> list[CandidateObservation]:
    rows: list[CandidateObservation] = []
    for day in observation_dates:
        rows.extend(repo.list_canonical_by_date(day))
    return rows


def _observation_link_index(
    observations: list[CandidateObservation],
) -> dict[tuple[str, date, datetime], str]:
    index: dict[tuple[str, date, datetime], str] = {}
    for obs in observations:
        if obs.semantic_compatibility_id is None:
            continue
        key = (obs.ticker.upper(), obs.snapshot_date, obs.captured_at)
        index[key] = str(obs.semantic_compatibility_id)
    return index


def _label_link_key(label: SignalForwardLabel) -> tuple[str, date, datetime] | None:
    if label.observation_captured_at is None:
        return None
    return (label.ticker.upper(), label.signal_date, label.observation_captured_at)


def _resolve_cohort(
    *,
    available_cohorts: tuple[str, ...],
    requested: str | None,
) -> tuple[str | None, str | None]:
    if requested is not None:
        requested = requested.strip()
        if not requested:
            return None, "semantic_compatibility_id is empty"
        if requested not in available_cohorts:
            return None, (
                f"requested semantic_compatibility_id not found in canonical "
                f"observations: {requested}"
            )
        return requested, None
    if not available_cohorts:
        return None, "no semantic_compatibility_id on canonical observations"
    if len(available_cohorts) > 1:
        return None, "mixed_semantic_cohorts"
    return available_cohorts[0], None


def _collapse_independent_labeled_targets(
    labels: tuple[SignalForwardLabel, ...],
) -> tuple[tuple[SignalForwardLabel, ...], int]:
    """One row per (ticker, signal_date, horizon); latest observation_captured_at wins."""
    winners: dict[tuple[str, date, str], SignalForwardLabel] = {}
    for label in labels:
        key = (label.ticker.upper(), label.signal_date, label.horizon.value)
        current = winners.get(key)
        if current is None:
            winners[key] = label
            continue
        current_ts = current.observation_captured_at or datetime.min
        candidate_ts = label.observation_captured_at or datetime.min
        if candidate_ts > current_ts:
            winners[key] = label
        elif candidate_ts == current_ts and label.ticker.upper() < current.ticker.upper():
            winners[key] = label
    independent = tuple(
        sorted(
            winners.values(),
            key=lambda row: (
                row.signal_date,
                row.observation_captured_at.isoformat()
                if row.observation_captured_at
                else "",
                row.ticker,
            ),
        )
    )
    collapsed = max(0, len(labels) - len(independent))
    return independent, collapsed


def _observation_matches_target(
    observation: CandidateObservation,
    target: SignalReadinessTarget,
) -> bool:
    fingerprint = SignalObservationFingerprint.from_dict(
        observation.payload.get("sub_signal_fingerprint") or {}
    )
    return _fingerprint_matches_target(fingerprint, target)


def _label_matches_target(
    label: SignalForwardLabel,
    target: SignalReadinessTarget,
) -> bool:
    return label.horizon is target.horizon and _fingerprint_matches_target(
        label.fingerprint,
        target,
    )


def _fingerprint_matches_target(
    fingerprint: SignalObservationFingerprint,
    target: SignalReadinessTarget,
) -> bool:
    if (fingerprint.ticker_profile_label or "").lower() != target.profile.lower():
        return False
    if target.market_cap_bucket is not None:
        if (fingerprint.tp_market_cap_bucket or "").lower() != target.market_cap_bucket.lower():
            return False
    if (fingerprint.alpha_trigger_horizon or "").upper() != target.horizon.value:
        return False
    setup_family = (fingerprint.setup_family or "").lower()
    if not setup_family:
        return False
    if target.setup_family.lower() == "accumulation":
        return setup_family in _ACCUMULATION_SETUP_FAMILIES
    return setup_family == target.setup_family.lower()


def _split_is_oos(
    labels: tuple[SignalForwardLabel, ...],
) -> tuple[tuple[SignalForwardLabel, ...], tuple[SignalForwardLabel, ...]]:
    ordered = tuple(
        sorted(
            labels,
            key=lambda label: (
                label.signal_date,
                (
                    label.observation_captured_at.isoformat()
                    if label.observation_captured_at
                    else ""
                ),
                label.ticker,
            ),
        )
    )
    if not ordered:
        return (), ()
    oos_count = max(1, round(len(ordered) * _OOS_FRACTION))
    return ordered[:-oos_count], ordered[-oos_count:]


def _profit_factor(labels: tuple[SignalForwardLabel, ...]) -> float | None:
    returns = [
        float(label.close_return)
        for label in labels
        if label.close_return is not None
    ]
    if not returns:
        return None
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value < 0))
    if losses == 0:
        return float("inf") if gains > 0 else None
    return round(gains / losses, 4)


def _average_return(labels: tuple[SignalForwardLabel, ...]) -> float | None:
    returns = [
        float(label.close_return)
        for label in labels
        if label.close_return is not None
    ]
    if not returns:
        return None
    return round(sum(returns) / len(returns), 4)


def _blockers(
    *,
    observation_dates: tuple[date, ...],
    target_filter_count: int,
    label_count: int,
    labeled_target_count: int,
    is_count: int,
    oos_count: int,
    oos_profit_factor: float | None,
    oos_average_return: float | None,
    oos_rows: tuple[SignalForwardLabel, ...],
    cohort_blocker: str | None,
) -> list[str]:
    blockers: list[str] = []
    if cohort_blocker is not None:
        blockers.append(cohort_blocker)
    if not observation_dates:
        blockers.append("no candidate observations saved")
    if target_filter_count == 0:
        blockers.append("latest observations have no rows matching target filter")
    if label_count == 0:
        blockers.append("no forward labels generated yet")
    if labeled_target_count == 0:
        blockers.append("no available labels match target filter")
    if is_count < _PATCH_MIN_IS_LABELS:
        blockers.append(f"IS labeled target count {is_count} < {_PATCH_MIN_IS_LABELS}")
    if oos_count < _DIAGNOSTIC_MIN_OOS_LABELS:
        blockers.append(
            f"OOS labeled target count {oos_count} < diagnostic-ready minimum "
            f"{_DIAGNOSTIC_MIN_OOS_LABELS}"
        )
    elif oos_count < _PATCH_MIN_OOS_LABELS:
        blockers.append(
            f"OOS labeled target count {oos_count} < patch-eligible minimum "
            f"{_PATCH_MIN_OOS_LABELS}"
        )
    if oos_count >= _DIAGNOSTIC_MIN_OOS_LABELS:
        if oos_profit_factor is None:
            blockers.append("OOS profit factor unavailable")
        elif oos_profit_factor < _PATCH_MIN_OOS_PROFIT_FACTOR:
            blockers.append(
                f"OOS profit factor {oos_profit_factor:.2f} < "
                f"{_PATCH_MIN_OOS_PROFIT_FACTOR:.2f}"
            )
        if oos_average_return is None:
            blockers.append("OOS average return unavailable")
        elif oos_average_return < _PATCH_MIN_OOS_AVERAGE_RETURN:
            blockers.append(
                f"OOS average return {oos_average_return:.2f} < "
                f"{_PATCH_MIN_OOS_AVERAGE_RETURN:.2f}"
            )
        if not _has_regime_attribution(oos_rows):
            blockers.append("OOS labels missing market regime attribution")
        if not _has_signal_authority_coverage_attribution(oos_rows):
            blockers.append("OOS labels missing signal_authority_coverage attribution")
    return blockers


def _notes(
    *,
    latest_observation_count: int,
    raw_latest_observation_count: int,
    is_diagnostic: bool = False,
    collapsed_duplicates: int = 0,
    selected_cohort: str | None = None,
) -> list[str]:
    result: list[str] = [
        f"oos_split={_OOS_SPLIT_MODE} (diagnostic only; not promotion-grade)",
        "promotion_eligible=false (DQ-006 lean; calibration floors != production authority)",
    ]
    if selected_cohort is not None:
        result.append(f"selected_semantic_compatibility_id={selected_cohort}")
    if is_diagnostic:
        result.append(
            "Diagnostic target: market-cap bucket not required; "
            "canonical large-cap target remains blocked."
        )
    if raw_latest_observation_count != latest_observation_count:
        result.append(
            "Multi-window observations collapsed to latest per ticker for "
            "readiness to avoid duplicate ticker/day labels."
        )
    if collapsed_duplicates:
        result.append(
            f"Collapsed {collapsed_duplicates} duplicate labeled-target row(s) to "
            "one independent sample per (ticker, signal_date, horizon)."
        )
    return result


def _has_regime_attribution(labels: tuple[SignalForwardLabel, ...]) -> bool:
    return all(label.fingerprint.market_regime.get("regime") for label in labels)


def _has_signal_authority_coverage_attribution(
    labels: tuple[SignalForwardLabel, ...],
) -> bool:
    return all(
        label.fingerprint.signal_authority_coverage is not None for label in labels
    )
