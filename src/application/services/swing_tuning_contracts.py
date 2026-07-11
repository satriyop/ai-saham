"""Deterministic DTOs and contracts for swing attribution-driven tuning.

Intent:
    This module defines the DTOs, constants, and apply-block guardrail used by
    swing attribution-driven tuning. Proposal and config-diff building are
    implemented in sibling application services and re-exported here for
    public import compatibility. It never generates YAML diffs, calls AI,
    applies changes, or mutates config.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

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
    tuning_config_diff_item_interpretation,
    tuning_config_diff_rejection_interpretation,
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


# Compatibility re-exports: implementations live in sibling modules to keep
# this module focused on DTOs/contracts. Imported at the bottom so DTOs are
# already defined when those modules import them back.
from src.application.services.swing_tuning_config_diff_draft_builder import (  # noqa: E402
    build_tuning_config_diff_draft,
)
from src.application.services.swing_tuning_proposal_builder import (  # noqa: E402
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
)
