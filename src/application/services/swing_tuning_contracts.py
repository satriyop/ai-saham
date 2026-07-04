"""Deterministic contracts for swing attribution-driven tuning.

Intent:
    This module consumes swing backtest attribution summaries and builds guarded
    tuning handoff artifacts. It may select narrowly bounded deterministic
    dry-run values for human review. It never generates YAML diffs, calls AI,
    applies changes, or mutates config.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.application.services.swing_backtest_attribution import (
    AttributionGroupStat,
    CandidateAttributionStat,
    SwingBacktestAttributionSummary,
)
from src.application.services.swing_tuning_config_paths import (
    TuningConfigPath,
    TuningConfigValueResolution,
    expand_tuning_config_paths,
    parse_tuning_config_path,
    resolve_tuning_config_value,
    validate_tuning_target_paths,
)
from src.application.services.swing_tuning_diff_policy import (
    TuningTargetClassification,
    TuningValueSuggestion,
    build_tuning_config_diff_review_checklist,
    build_tuning_config_diff_summary,
    suggest_tuning_value,
    tuning_config_diff_item_interpretation,
    tuning_config_diff_rejection_interpretation,
    tuning_diff_item_priority,
    value_selection_policy_for_rejection,
)

TUNING_CONFIG_DIFF_NO_APPLY_INTENT = "config_diff_schema_only_no_apply"

__all__ = (
    "TUNING_CONFIG_DIFF_NO_APPLY_INTENT",
    "TuningConfigDiffDraft",
    "TuningConfigDiffItem",
    "TuningConfigDiffRejection",
    "TuningConfigPath",
    "TuningConfigValueResolution",
    "TuningEvidenceSnapshot",
    "TuningProposalCandidate",
    "TuningProposalDraft",
    "TuningProposalRejection",
    "TuningReadinessPlan",
    "TuningTargetClassification",
    "TuningValueSuggestion",
    "assert_tuning_config_diff_apply_block",
    "build_tuning_config_diff_draft",
    "build_tuning_proposal_draft",
    "build_tuning_readiness_plan",
    "expand_tuning_config_paths",
    "parse_tuning_config_path",
    "resolve_tuning_config_value",
    "validate_tuning_target_paths",
)


@dataclass(frozen=True)
class TuningReadinessPlan:
    """Deterministic preflight for attribution-driven YAML tuning."""

    intent: str
    status: str
    can_propose_changes: bool
    blocked_reasons: tuple[str, ...]
    allowed_evidence_scopes: tuple[str, ...]
    allowed_config_families: tuple[str, ...]
    target_count: int
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "status": self.status,
            "can_propose_changes": self.can_propose_changes,
            "blocked_reasons": list(self.blocked_reasons),
            "allowed_evidence_scopes": list(self.allowed_evidence_scopes),
            "allowed_config_families": list(self.allowed_config_families),
            "target_count": self.target_count,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class TuningProposalCandidate:
    """Dry-run review target selected from attribution evidence."""

    dimension: str
    config_family: str
    source_scope: str
    yaml_paths: tuple[str, ...]
    allowed_use: str
    evidence_buckets: tuple[str, ...]
    evidence_strength: str
    priority: int
    evidence_sample_count: int
    evidence_return_spread_pct: float | None
    proposed_action: str = "review_threshold_or_weight_no_yaml_diff"
    warning: str | None = None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "config_family": self.config_family,
            "source_scope": self.source_scope,
            "yaml_paths": list(self.yaml_paths),
            "allowed_use": self.allowed_use,
            "evidence_buckets": list(self.evidence_buckets),
            "evidence_strength": self.evidence_strength,
            "priority": self.priority,
            "evidence_sample_count": self.evidence_sample_count,
            "evidence_return_spread_pct": self.evidence_return_spread_pct,
            "proposed_action": self.proposed_action,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class TuningProposalRejection:
    """Rejected tuning target with deterministic reason."""

    dimension: str
    config_family: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "config_family": self.config_family,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TuningProposalDraft:
    """Deterministic target-selection proposal; never chooses values or mutates config."""

    intent: str
    status: str
    readiness_status: str
    can_generate_yaml_diff: bool
    requires_human_review: bool
    candidate_changes: tuple[TuningProposalCandidate, ...]
    rejected_changes: tuple[TuningProposalRejection, ...]
    evidence_notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "status": self.status,
            "readiness_status": self.readiness_status,
            "can_generate_yaml_diff": self.can_generate_yaml_diff,
            "requires_human_review": self.requires_human_review,
            "candidate_changes": [
                candidate.to_dict() for candidate in self.candidate_changes
            ],
            "rejected_changes": [
                rejection.to_dict() for rejection in self.rejected_changes
            ],
            "evidence_notes": list(self.evidence_notes),
        }


@dataclass(frozen=True)
class TuningEvidenceSnapshot:
    """Compact attribution evidence behind one tuning config diff row."""

    sample_count: int
    return_spread_pct: float | None
    priority: int
    evidence_strength: str
    proposed_action: str
    evidence_buckets: tuple[str, ...]

    @classmethod
    def from_candidate(
        cls,
        candidate: TuningProposalCandidate,
    ) -> TuningEvidenceSnapshot:
        return cls(
            sample_count=candidate.evidence_sample_count,
            return_spread_pct=candidate.evidence_return_spread_pct,
            priority=candidate.priority,
            evidence_strength=candidate.evidence_strength,
            proposed_action=candidate.proposed_action,
            evidence_buckets=candidate.evidence_buckets,
        )

    def to_dict(self) -> dict:
        return {
            "sample_count": self.sample_count,
            "return_spread_pct": self.return_spread_pct,
            "priority": self.priority,
            "evidence_strength": self.evidence_strength,
            "proposed_action": self.proposed_action,
            "evidence_buckets": list(self.evidence_buckets),
        }


@dataclass(frozen=True)
class TuningConfigDiffItem:
    """Dry-run current/proposed value row for human review."""

    target_path: str
    current_value: object | None
    proposed_value: object | None
    rationale: str
    evidence_dimension: str
    confidence: str
    status: str
    value_selection_policy: str
    parsed_target_path: TuningConfigPath | None = None
    evidence_dimensions: tuple[str, ...] = ()
    evidence_snapshot: TuningEvidenceSnapshot | None = None

    @property
    def target_classification(self) -> TuningTargetClassification:
        return TuningTargetClassification.from_path(self.parsed_target_path)

    @property
    def interpretation(self) -> str:
        return tuning_config_diff_item_interpretation(
            self.status,
            self.value_selection_policy,
        )

    def to_dict(self) -> dict:
        evidence_dimensions = self.evidence_dimensions or (self.evidence_dimension,)
        return {
            "target_path": self.target_path,
            "parsed_target_path": (
                self.parsed_target_path.to_dict()
                if self.parsed_target_path is not None
                else None
            ),
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "rationale": self.rationale,
            "evidence_dimension": self.evidence_dimension,
            "evidence_dimensions": list(evidence_dimensions),
            "confidence": self.confidence,
            "status": self.status,
            "value_selection_policy": self.value_selection_policy,
            "interpretation": self.interpretation,
            "target_classification": self.target_classification.to_dict(),
            "evidence_snapshot": (
                self.evidence_snapshot.to_dict()
                if self.evidence_snapshot is not None
                else None
            ),
        }


@dataclass(frozen=True)
class TuningConfigDiffRejection:
    """Rejected config diff candidate with deterministic reason."""

    target_path: str
    evidence_dimension: str
    reason: str
    value_selection_policy: str
    parsed_target_path: TuningConfigPath | None = None

    @property
    def interpretation(self) -> str:
        return tuning_config_diff_rejection_interpretation(
            self.value_selection_policy,
        )

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "parsed_target_path": (
                self.parsed_target_path.to_dict()
                if self.parsed_target_path is not None
                else None
            ),
            "evidence_dimension": self.evidence_dimension,
            "reason": self.reason,
            "value_selection_policy": self.value_selection_policy,
            "interpretation": self.interpretation,
        }


@dataclass(frozen=True)
class TuningConfigDiffDraft:
    """Guarded current/proposed value envelope; never applies config changes."""

    intent: str
    status: str
    proposal_status: str
    can_apply: bool
    requires_human_review: bool
    diff_items: tuple[TuningConfigDiffItem, ...]
    rejected_items: tuple[TuningConfigDiffRejection, ...]
    notes: tuple[str, ...]
    summary: dict[str, object] | None = None
    review_checklist: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "status": self.status,
            "proposal_status": self.proposal_status,
            "can_apply": self.can_apply,
            "requires_human_review": self.requires_human_review,
            "diff_items": [item.to_dict() for item in self.diff_items],
            "rejected_items": [
                rejection.to_dict() for rejection in self.rejected_items
            ],
            "summary": self.summary or build_tuning_config_diff_summary(
                self.diff_items,
                self.rejected_items,
            ),
            "review_checklist": list(
                self.review_checklist
                or build_tuning_config_diff_review_checklist(
                    self.diff_items,
                    self.rejected_items,
                )
            ),
            "notes": list(self.notes),
        }


def assert_tuning_config_diff_apply_block(
    draft: TuningConfigDiffDraft,
) -> TuningConfigDiffDraft:
    """Assert that a tuning config diff draft remains non-applyable."""
    violations: list[str] = []
    if draft.intent != TUNING_CONFIG_DIFF_NO_APPLY_INTENT:
        violations.append("intent_must_be_no_apply")
    if draft.can_apply:
        violations.append("can_apply_must_be_false")
    if not draft.requires_human_review:
        violations.append("requires_human_review_must_be_true")
    if violations:
        raise ValueError(
            "Tuning config diff apply block violated: "
            + ", ".join(violations)
        )
    return draft


@dataclass(frozen=True)
class _DimensionEvidence:
    buckets: tuple[str, ...]
    sample_count: int
    return_spread_pct: float | None
    strength: str
    priority: int


def build_tuning_readiness_plan(
    summary: SwingBacktestAttributionSummary,
) -> TuningReadinessPlan:
    """Build deterministic readiness output for tuning, without proposing edits."""
    quality = summary.sample_quality
    evidence_scopes: list[str] = []
    if quality.trade_sample_ready:
        evidence_scopes.append("completed_trades")
    if quality.candidate_sample_ready:
        evidence_scopes.append("screened_candidates")

    allowed_targets = tuple(
        target
        for target in summary.tuning_targets
        if _target_scope_allowed(target.source_scope, evidence_scopes)
    )
    config_families = tuple(
        sorted({target.config_family for target in allowed_targets})
    )
    can_propose_changes = quality.status != "INSUFFICIENT_SAMPLE"
    notes = (
        "Readiness plan is deterministic and reporting-only.",
        "No AI proposal, YAML diff, or config mutation is generated.",
        *quality.notes,
    )

    return TuningReadinessPlan(
        intent="readiness_gate_for_future_tuning_only",
        status=quality.status,
        can_propose_changes=can_propose_changes,
        blocked_reasons=() if can_propose_changes else quality.notes,
        allowed_evidence_scopes=tuple(evidence_scopes),
        allowed_config_families=config_families,
        target_count=len(allowed_targets),
        notes=notes,
    )


def build_tuning_proposal_draft(
    summary: SwingBacktestAttributionSummary,
) -> TuningProposalDraft:
    """Build deterministic target-selection output without parameter values."""
    readiness = build_tuning_readiness_plan(summary)
    notes = _unique_strings((
        "Draft is deterministic and dry-run only.",
        "Candidate changes identify review targets, not parameter values.",
        "No AI proposal, YAML diff, or config mutation is generated.",
        *readiness.notes,
    ))
    if not readiness.can_propose_changes:
        return TuningProposalDraft(
            intent="dry_run_tuning_proposal_contract_only",
            status="BLOCKED",
            readiness_status=readiness.status,
            can_generate_yaml_diff=False,
            requires_human_review=True,
            candidate_changes=(),
            rejected_changes=tuple(
                TuningProposalRejection(
                    dimension=target.dimension,
                    config_family=target.config_family,
                    reason="Readiness gate blocks tuning proposals.",
                )
                for target in summary.tuning_targets
            ),
            evidence_notes=notes,
        )

    evidence_by_dimension = _evidence_by_dimension(summary)
    candidate_changes: list[TuningProposalCandidate] = []
    rejected_changes: list[TuningProposalRejection] = []

    for target in summary.tuning_targets:
        if not _target_scope_allowed(
            target.source_scope,
            list(readiness.allowed_evidence_scopes),
        ):
            rejected_changes.append(
                TuningProposalRejection(
                    dimension=target.dimension,
                    config_family=target.config_family,
                    reason="Target source scope is not ready.",
                )
            )
            continue

        evidence = evidence_by_dimension.get(target.dimension)
        if evidence is None or not evidence.buckets:
            rejected_changes.append(
                TuningProposalRejection(
                    dimension=target.dimension,
                    config_family=target.config_family,
                    reason="No attribution buckets are available for this dimension.",
                )
            )
            continue

        candidate_changes.append(
            TuningProposalCandidate(
                dimension=target.dimension,
                config_family=target.config_family,
                source_scope=target.source_scope,
                yaml_paths=target.yaml_paths,
                allowed_use=target.allowed_use,
                evidence_buckets=evidence.buckets,
                evidence_strength=evidence.strength,
                priority=evidence.priority,
                evidence_sample_count=evidence.sample_count,
                evidence_return_spread_pct=evidence.return_spread_pct,
                warning=target.warning,
            )
        )

    candidate_changes.sort(
        key=lambda candidate: (
            candidate.priority,
            candidate.evidence_sample_count,
            candidate.dimension,
        ),
        reverse=True,
    )
    status = "READY_FOR_HUMAN_REVIEW" if candidate_changes else "NO_EVIDENCE_TARGETS"
    return TuningProposalDraft(
        intent="dry_run_tuning_proposal_contract_only",
        status=status,
        readiness_status=readiness.status,
        can_generate_yaml_diff=False,
        requires_human_review=True,
        candidate_changes=tuple(candidate_changes),
        rejected_changes=tuple(rejected_changes),
        evidence_notes=notes,
    )


def build_tuning_config_diff_draft(
    summary: SwingBacktestAttributionSummary,
    config_root: Path | str = Path("."),
    active_setups: frozenset[str] | None = None,
) -> TuningConfigDiffDraft:
    """Build a guarded dry-run config-diff schema without mutating config.

    active_setups: when provided, only include proposal paths for the named
    setups (e.g. frozenset({"foreign-bounce"})). Prevents evidence from one
    setup's backtest contaminating unrelated setup parameter proposals.
    """
    proposal = build_tuning_proposal_draft(summary)
    notes = _unique_strings((
        "Config diff draft is dry-run only.",
        "Current values are resolved only for concrete YAML paths.",
        "Proposed values require deterministic guarded value-selection.",
        "No YAML diff, AI proposal, apply step, or config mutation is generated.",
        *proposal.evidence_notes,
    ))

    if proposal.status == "BLOCKED":
        rejected_items_tuple = tuple(
            TuningConfigDiffRejection(
                target_path="N/A",
                evidence_dimension=rejection.dimension,
                reason=f"Proposal target rejected: {rejection.reason}",
                value_selection_policy="INSUFFICIENT_EVIDENCE",
            )
            for rejection in proposal.rejected_changes
        )
        return assert_tuning_config_diff_apply_block(
            TuningConfigDiffDraft(
                intent=TUNING_CONFIG_DIFF_NO_APPLY_INTENT,
                status="BLOCKED",
                proposal_status=proposal.status,
                can_apply=False,
                requires_human_review=True,
                diff_items=(),
                rejected_items=rejected_items_tuple,
                summary=build_tuning_config_diff_summary(
                    (),
                    rejected_items_tuple,
                ),
                review_checklist=build_tuning_config_diff_review_checklist(
                    (),
                    rejected_items_tuple,
                ),
                notes=notes,
            ),
        )

    diff_items: list[TuningConfigDiffItem] = []
    rejected_items: list[TuningConfigDiffRejection] = []
    for candidate in proposal.candidate_changes:
        for target_path in candidate.yaml_paths:
            for expanded_target_path in expand_tuning_config_paths(
                target_path,
                config_root=config_root,
                active_setups=active_setups,
            ):
                parsed_target_path = parse_tuning_config_path(expanded_target_path)
                resolution = resolve_tuning_config_value(
                    parsed_target_path,
                    config_root=config_root,
                )
                if not resolution.resolved:
                    rejected_items.append(
                        TuningConfigDiffRejection(
                            target_path=expanded_target_path,
                            parsed_target_path=parsed_target_path,
                            evidence_dimension=candidate.dimension,
                            reason=resolution.unresolved_reason
                            or "config_value_not_resolved",
                            value_selection_policy=value_selection_policy_for_rejection(
                                resolution.unresolved_reason,
                            ),
                        )
                    )
                    continue

                suggestion = suggest_tuning_value(candidate, resolution)
                diff_items.append(
                    TuningConfigDiffItem(
                        target_path=expanded_target_path,
                        parsed_target_path=parsed_target_path,
                        current_value=resolution.current_value,
                        proposed_value=suggestion.proposed_value,
                        rationale=suggestion.rationale,
                        evidence_dimension=candidate.dimension,
                        confidence=suggestion.confidence,
                        status=suggestion.status,
                        value_selection_policy=suggestion.value_selection_policy,
                        evidence_snapshot=TuningEvidenceSnapshot.from_candidate(
                            candidate
                        ),
                    )
                )

    has_proposed_values = any(
        item.proposed_value is not None for item in diff_items
    )
    deduped_diff_items = _dedupe_tuning_diff_items(diff_items)
    rejected_items_tuple = tuple(rejected_items)
    return assert_tuning_config_diff_apply_block(
        TuningConfigDiffDraft(
            intent=TUNING_CONFIG_DIFF_NO_APPLY_INTENT,
            status=(
                "PROPOSED_VALUES_DRY_RUN"
                if has_proposed_values
                else "READ_ONLY_VALUES"
                if diff_items
                else "SCHEMA_ONLY"
            ),
            proposal_status=proposal.status,
            can_apply=False,
            requires_human_review=True,
            diff_items=deduped_diff_items,
            rejected_items=rejected_items_tuple,
            summary=build_tuning_config_diff_summary(
                deduped_diff_items,
                rejected_items_tuple,
            ),
            review_checklist=build_tuning_config_diff_review_checklist(
                deduped_diff_items,
                rejected_items_tuple,
            ),
            notes=notes,
        )
    )


def _dedupe_tuning_diff_items(
    diff_items: list[TuningConfigDiffItem],
) -> tuple[TuningConfigDiffItem, ...]:
    grouped: dict[str, list[TuningConfigDiffItem]] = {}
    for item in diff_items:
        grouped.setdefault(item.target_path, []).append(item)

    deduped: list[TuningConfigDiffItem] = []
    for target_path in sorted(grouped):
        rows = grouped[target_path]
        selected = _select_tuning_diff_item(rows)
        evidence_dimensions = _unique_strings(
            item.evidence_dimension for item in rows
        )
        deduped.append(
            TuningConfigDiffItem(
                target_path=selected.target_path,
                parsed_target_path=selected.parsed_target_path,
                current_value=selected.current_value,
                proposed_value=selected.proposed_value,
                rationale=_merged_tuning_diff_rationale(
                    selected.rationale,
                    evidence_dimensions,
                ),
                evidence_dimension=selected.evidence_dimension,
                evidence_dimensions=evidence_dimensions,
                evidence_snapshot=selected.evidence_snapshot,
                confidence=selected.confidence,
                status=selected.status,
                value_selection_policy=selected.value_selection_policy,
            )
        )
    return tuple(deduped)


def _select_tuning_diff_item(
    rows: list[TuningConfigDiffItem],
) -> TuningConfigDiffItem:
    return max(
        enumerate(rows),
        key=lambda indexed: (
            tuning_diff_item_priority(indexed[1]),
            -indexed[0],
        ),
    )[1]


def _merged_tuning_diff_rationale(
    rationale: str,
    evidence_dimensions: tuple[str, ...],
) -> str:
    if len(evidence_dimensions) <= 1:
        return rationale
    return (
        f"{rationale} Evidence dimensions: "
        f"{', '.join(evidence_dimensions)}."
    )


def _evidence_by_dimension(
    summary: SwingBacktestAttributionSummary,
) -> dict[str, _DimensionEvidence]:
    evidence: dict[str, _DimensionEvidence] = {}
    stats = tuple(summary.group_stats) + tuple(summary.candidate_group_stats)
    dimensions = sorted({stat.dimension for stat in stats})
    for dimension in dimensions:
        dimension_stats = [stat for stat in stats if stat.dimension == dimension]
        top_stats = sorted(
            dimension_stats,
            key=lambda stat: (
                _stat_sample_count(stat),
                _stat_return(stat) or 0.0,
                stat.bucket,
            ),
            reverse=True,
        )[:3]
        sample_count = sum(_stat_sample_count(stat) for stat in dimension_stats)
        returns = tuple(
            value
            for value in (_stat_return(stat) for stat in dimension_stats)
            if value is not None
        )
        spread = round(max(returns) - min(returns), 4) if returns else None
        strength = _evidence_strength(
            sample_count=sample_count,
            bucket_count=len(dimension_stats),
            return_spread_pct=spread,
            min_sample_size=summary.sample_quality.min_sample_size,
        )
        evidence[dimension] = _DimensionEvidence(
            buckets=tuple(_format_evidence_bucket(stat) for stat in top_stats),
            sample_count=sample_count,
            return_spread_pct=spread,
            strength=strength,
            priority=_evidence_priority(
                sample_count=sample_count,
                return_spread_pct=spread,
                strength=strength,
            ),
        )
    return evidence


def _evidence_strength(
    *,
    sample_count: int,
    bucket_count: int,
    return_spread_pct: float | None,
    min_sample_size: int,
) -> str:
    spread = return_spread_pct or 0.0
    if sample_count >= min_sample_size * 2 and bucket_count >= 2 and spread >= 2.0:
        return "HIGH"
    if sample_count >= min_sample_size and (bucket_count >= 2 or spread >= 1.0):
        return "MEDIUM"
    if sample_count >= min_sample_size:
        return "LOW"
    return "INSUFFICIENT"


def _evidence_priority(
    *,
    sample_count: int,
    return_spread_pct: float | None,
    strength: str,
) -> int:
    strength_bonus = {
        "HIGH": 300,
        "MEDIUM": 200,
        "LOW": 100,
        "INSUFFICIENT": 0,
    }[strength]
    spread_bonus = min(int((return_spread_pct or 0.0) * 10), 100)
    sample_bonus = min(sample_count, 100)
    return strength_bonus + spread_bonus + sample_bonus


def _stat_sample_count(stat: AttributionGroupStat | CandidateAttributionStat) -> int:
    return getattr(stat, "trade_count", getattr(stat, "observation_count", 0))


def _stat_return(stat: AttributionGroupStat | CandidateAttributionStat) -> float | None:
    return getattr(
        stat,
        "avg_return_pct",
        getattr(stat, "avg_forward_return_pct", None),
    )


def _format_evidence_bucket(
    stat: AttributionGroupStat | CandidateAttributionStat,
) -> str:
    avg_return = _stat_return(stat)
    avg_text = "N/A" if avg_return is None else f"{avg_return:+.2f}%"
    return f"{stat.bucket} | n={_stat_sample_count(stat)} | avg={avg_text}"


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _target_scope_allowed(source_scope: str, evidence_scopes: list[str]) -> bool:
    if source_scope == "completed_trades_and_screened_candidates":
        return bool({"completed_trades", "screened_candidates"} & set(evidence_scopes))
    return source_scope in evidence_scopes
