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

import yaml

from src.application.services.swing_backtest_attribution import (
    AttributionGroupStat,
    CandidateAttributionStat,
    SwingBacktestAttributionSummary,
)

TUNING_CONFIG_DIFF_NO_APPLY_INTENT = "config_diff_schema_only_no_apply"
_SETUP_GATES_WILDCARD_PATH = "setups.*.gates"
_SETUP_PARTIAL_MAX_FAILED_GATES_WILDCARD_PATH = "setups.*.partial_max_failed_gates"


@dataclass(frozen=True)
class TuningConfigPath:
    """Structured YAML path target for future config diff generation."""

    raw: str
    file_path: str
    document_path: str

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "file_path": self.file_path,
            "document_path": self.document_path,
        }


@dataclass(frozen=True)
class TuningConfigValueResolution:
    """Read-only result of resolving a tuning config path."""

    target_path: TuningConfigPath
    resolved: bool
    current_value: object | None = None
    unresolved_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path.to_dict(),
            "resolved": self.resolved,
            "current_value": self.current_value,
            "unresolved_reason": self.unresolved_reason,
        }


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
        }


@dataclass(frozen=True)
class TuningConfigDiffRejection:
    """Rejected config diff candidate with deterministic reason."""

    target_path: str
    evidence_dimension: str
    reason: str
    value_selection_policy: str
    parsed_target_path: TuningConfigPath | None = None

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
        }


@dataclass(frozen=True)
class TuningValueSuggestion:
    """Deterministic value-selection result for a config diff item."""

    proposed_value: object | None
    rationale: str
    confidence: str
    status: str
    value_selection_policy: str


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
) -> TuningConfigDiffDraft:
    """Build a guarded dry-run config-diff schema without mutating config."""
    proposal = build_tuning_proposal_draft(summary)
    notes = _unique_strings((
        "Config diff draft is dry-run only.",
        "Current values are resolved only for concrete YAML paths.",
        "Proposed values require deterministic guarded value-selection.",
        "No YAML diff, AI proposal, apply step, or config mutation is generated.",
        *proposal.evidence_notes,
    ))

    if proposal.status == "BLOCKED":
        return assert_tuning_config_diff_apply_block(
            TuningConfigDiffDraft(
                intent=TUNING_CONFIG_DIFF_NO_APPLY_INTENT,
                status="BLOCKED",
                proposal_status=proposal.status,
                can_apply=False,
                requires_human_review=True,
                diff_items=(),
                rejected_items=tuple(
                    TuningConfigDiffRejection(
                        target_path="N/A",
                        evidence_dimension=rejection.dimension,
                        reason=f"Proposal target rejected: {rejection.reason}",
                        value_selection_policy="INSUFFICIENT_EVIDENCE",
                    )
                    for rejection in proposal.rejected_changes
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
                            value_selection_policy=_value_selection_policy_for_rejection(
                                resolution.unresolved_reason,
                            ),
                        )
                    )
                    continue

                suggestion = _suggest_tuning_value(candidate, resolution)
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
                    )
                )

    has_proposed_values = any(
        item.proposed_value is not None for item in diff_items
    )
    deduped_diff_items = _dedupe_tuning_diff_items(diff_items)
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
            rejected_items=tuple(rejected_items),
            notes=notes,
        )
    )


def parse_tuning_config_path(raw_path: str) -> TuningConfigPath:
    """Parse a tuning target path in file.yaml:document.path format."""
    file_path, separator, document_path = raw_path.partition(":")
    if not separator or not file_path.strip() or not document_path.strip():
        raise ValueError(
            "Tuning config path must use 'file.yaml:document.path' format."
        )
    normalized_file_path = file_path.strip()
    if not normalized_file_path.endswith((".yaml", ".yml")):
        raise ValueError("Tuning config path file must end with .yaml or .yml.")
    return TuningConfigPath(
        raw=raw_path,
        file_path=normalized_file_path,
        document_path=document_path.strip(),
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
            _tuning_diff_item_priority(indexed[1]),
            -indexed[0],
        ),
    )[1]


def _tuning_diff_item_priority(item: TuningConfigDiffItem) -> int:
    if item.proposed_value is not None:
        return 100
    return {
        "DETERMINISTIC_VALUE_SELECTED": 100,
        "NO_DETERMINISTIC_DIRECTION": 80,
        "INSUFFICIENT_EVIDENCE": 70,
        "NO_UNAMBIGUOUS_DIRECTION": 60,
        "NON_NUMERIC_CURRENT_VALUE": 50,
    }.get(item.value_selection_policy, 10)


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


def expand_tuning_config_paths(
    raw_path: str,
    config_root: Path | str = Path("."),
) -> tuple[str, ...]:
    """Expand allowlisted wildcard tuning paths into concrete YAML paths."""
    parsed_path = parse_tuning_config_path(raw_path)
    if "*" not in parsed_path.document_path:
        return (parsed_path.raw,)

    if parsed_path.file_path != "config/swing_setups.yaml":
        return (parsed_path.raw,)

    if parsed_path.document_path == _SETUP_GATES_WILDCARD_PATH:
        return _expand_swing_setup_gate_paths(parsed_path, config_root)

    if parsed_path.document_path == _SETUP_PARTIAL_MAX_FAILED_GATES_WILDCARD_PATH:
        return _expand_swing_setup_partial_gate_paths(parsed_path, config_root)

    return (parsed_path.raw,)


def validate_tuning_target_paths(summary: SwingBacktestAttributionSummary) -> tuple[str, ...]:
    """Validate all tuning target YAML paths and return normalized raw paths."""
    parsed_paths: list[str] = []
    for target in summary.tuning_targets:
        for yaml_path in target.yaml_paths:
            parsed_paths.append(parse_tuning_config_path(yaml_path).raw)
    return tuple(parsed_paths)


def resolve_tuning_config_value(
    target_path: TuningConfigPath,
    config_root: Path | str = Path("."),
) -> TuningConfigValueResolution:
    """Resolve a concrete YAML tuning path without mutating config."""
    if "*" in target_path.document_path:
        return TuningConfigValueResolution(
            target_path=target_path,
            resolved=False,
            unresolved_reason="wildcard_path_not_resolved",
        )

    root = Path(config_root)
    yaml_path = root / target_path.file_path
    if not yaml_path.exists():
        return TuningConfigValueResolution(
            target_path=target_path,
            resolved=False,
            unresolved_reason="config_file_not_found",
        )

    with yaml_path.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}

    current: object = document
    for part in target_path.document_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return TuningConfigValueResolution(
                target_path=target_path,
                resolved=False,
                unresolved_reason="document_path_not_found",
            )
        current = current[part]

    return TuningConfigValueResolution(
        target_path=target_path,
        resolved=True,
        current_value=current,
    )


def _expand_swing_setup_gate_paths(
    target_path: TuningConfigPath,
    config_root: Path | str,
) -> tuple[str, ...]:
    document = _load_yaml_document(target_path.file_path, config_root)
    setups = document.get("setups") if isinstance(document, dict) else None
    if not isinstance(setups, dict):
        return (target_path.raw,)

    expanded_paths: list[str] = []
    for setup_name, setup_config in setups.items():
        if not isinstance(setup_config, dict):
            continue
        gates = setup_config.get("gates")
        if not isinstance(gates, dict):
            continue
        for gate_name in gates:
            expanded_paths.append(
                f"{target_path.file_path}:setups.{setup_name}.gates.{gate_name}"
            )
    return tuple(expanded_paths) or (target_path.raw,)


def _expand_swing_setup_partial_gate_paths(
    target_path: TuningConfigPath,
    config_root: Path | str,
) -> tuple[str, ...]:
    document = _load_yaml_document(target_path.file_path, config_root)
    setups = document.get("setups") if isinstance(document, dict) else None
    if not isinstance(setups, dict):
        return (target_path.raw,)

    expanded_paths = tuple(
        f"{target_path.file_path}:setups.{setup_name}.partial_max_failed_gates"
        for setup_name, setup_config in setups.items()
        if isinstance(setup_config, dict)
        and "partial_max_failed_gates" in setup_config
    )
    return expanded_paths or (target_path.raw,)


def _load_yaml_document(
    file_path: str,
    config_root: Path | str,
) -> dict:
    yaml_path = Path(config_root) / file_path
    if not yaml_path.exists():
        return {}
    with yaml_path.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}
    return document if isinstance(document, dict) else {}


def _value_selection_policy_for_rejection(unresolved_reason: str | None) -> str:
    return {
        "wildcard_path_not_resolved": "WILDCARD_UNRESOLVED",
        "config_file_not_found": "CONFIG_FILE_NOT_FOUND",
        "document_path_not_found": "DOCUMENT_PATH_NOT_FOUND",
    }.get(unresolved_reason or "", "CONFIG_VALUE_NOT_RESOLVED")


def _suggest_tuning_value(
    candidate: TuningProposalCandidate,
    resolution: TuningConfigValueResolution,
) -> TuningValueSuggestion:
    """Select a bounded deterministic value only for narrow safe cases."""
    current_value = resolution.current_value
    if not _is_tunable_number(current_value):
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current value resolved, but only numeric non-boolean config "
                "values are eligible for deterministic value-selection."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="NON_NUMERIC_CURRENT_VALUE",
        )

    if candidate.evidence_strength != "HIGH":
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current value resolved, but evidence strength is not HIGH."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="INSUFFICIENT_EVIDENCE",
        )

    adjustment_direction = _deterministic_adjustment_direction(
        candidate,
        resolution.target_path,
    )
    if adjustment_direction is None:
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current numeric value resolved, but attribution buckets do not "
                "support a deterministic value direction for this path."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="NO_DETERMINISTIC_DIRECTION",
        )

    if adjustment_direction == 0:
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current numeric value resolved, but the path does not expose "
                "an eligible threshold/weight/exit direction."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="NO_UNAMBIGUOUS_DIRECTION",
        )

    proposed_value = _bounded_one_step_adjustment(
        current_value,
        adjustment_direction,
    )
    return TuningValueSuggestion(
        proposed_value=proposed_value,
        rationale=(
            "HIGH evidence and an eligible numeric path allow a bounded "
            "one-step deterministic dry-run proposal for human review."
        ),
        confidence="DETERMINISTIC_GUARDED",
        status="PROPOSED_VALUE_SELECTED",
        value_selection_policy="DETERMINISTIC_VALUE_SELECTED",
    )


def _is_tunable_number(value: object | None) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _deterministic_adjustment_direction(
    candidate: TuningProposalCandidate,
    target_path: TuningConfigPath,
) -> int | None:
    if _evidence_supports_tightening(candidate):
        return _tighten_adjustment_direction(target_path)
    if _evidence_supports_loosening(candidate):
        return _loosen_adjustment_direction(target_path)
    return None


def _tighten_adjustment_direction(target_path: TuningConfigPath) -> int:
    threshold_direction = _numeric_adjustment_direction(target_path)
    if threshold_direction != 0:
        return threshold_direction

    path = target_path.document_path.lower()
    if ".take_profit_pct" in path:
        return 1
    if ".stop_loss_pct" in path:
        return -1
    if path.endswith(".signal_multiplier"):
        return -1
    if path.endswith(".partial_max_failed_gates"):
        return -1
    return 0


def _loosen_adjustment_direction(target_path: TuningConfigPath) -> int:
    threshold_direction = _numeric_adjustment_direction(target_path)
    if threshold_direction != 0:
        return -threshold_direction

    path = target_path.document_path.lower()
    if ".take_profit_pct" in path:
        return -1
    if ".stop_loss_pct" in path:
        return 1
    if path.endswith(".signal_multiplier"):
        return 1
    if path.endswith(".partial_max_failed_gates"):
        return 1
    return 0


def _numeric_adjustment_direction(target_path: TuningConfigPath) -> int:
    leaf_name = target_path.document_path.rsplit(".", maxsplit=1)[-1].lower()
    if any(token in leaf_name for token in ("min", "floor", "required", "bullish")):
        return 1
    if any(token in leaf_name for token in ("max", "ceiling", "bearish")):
        return -1
    return 0


def _bounded_one_step_adjustment(value: object, direction: int) -> int | float:
    if isinstance(value, int) and not isinstance(value, bool):
        return value + direction
    numeric_value = float(value)
    return round(numeric_value + (0.5 * direction), 4)


def _evidence_supports_tightening(candidate: TuningProposalCandidate) -> bool:
    bucket_avgs = _evidence_bucket_avgs(candidate)
    if candidate.dimension in {
        "signal_strength",
        "candidate_signal_strength",
    }:
        strong_avg = bucket_avgs.get("STRONG")
        if strong_avg is None:
            return False
        return any(
            avg > strong_avg
            for label, avg in bucket_avgs.items()
            if label in {"MODERATE", "WEAK"}
        )
    if candidate.dimension in {
        "signal_score_bucket",
        "candidate_signal_score_bucket",
    }:
        high_avg = next(
            (
                avg
                for label, avg in bucket_avgs.items()
                if label.startswith("HIGH")
            ),
            None,
        )
        if high_avg is None:
            return False
        return any(
            avg > high_avg
            for label, avg in bucket_avgs.items()
            if label.startswith(("LOW", "MID"))
        )
    if candidate.dimension in {"candidate_setup_match", "setup_match"}:
        match_avg = bucket_avgs.get("MATCH")
        no_match_avg = bucket_avgs.get("NO_MATCH")
        return match_avg is not None and no_match_avg is not None and match_avg > no_match_avg
    if candidate.dimension == "setup_gate":
        return _setup_gate_pass_avg_beats_fail_avg(bucket_avgs)
    return False


def _evidence_supports_loosening(candidate: TuningProposalCandidate) -> bool:
    bucket_avgs = _evidence_bucket_avgs(candidate)
    if candidate.dimension in {"candidate_setup_match", "setup_match"}:
        match_avg = bucket_avgs.get("MATCH")
        no_match_avg = bucket_avgs.get("NO_MATCH")
        return match_avg is not None and no_match_avg is not None and no_match_avg > match_avg
    if candidate.dimension == "setup_gate":
        return _setup_gate_fail_avg_beats_pass_avg(bucket_avgs)
    if candidate.dimension == "candidate_risk_status":
        open_avg = bucket_avgs.get("OPEN")
        blocked_avg = bucket_avgs.get("BLOCKED")
        return blocked_avg is not None and open_avg is not None and blocked_avg > open_avg
    return False


def _evidence_bucket_avgs(
    candidate: TuningProposalCandidate,
) -> dict[str, float]:
    return {
        label: avg
        for label, avg in (
            _parse_evidence_bucket_avg(bucket)
            for bucket in candidate.evidence_buckets
        )
        if label and avg is not None
    }


def _setup_gate_pass_avg_beats_fail_avg(bucket_avgs: dict[str, float]) -> bool:
    gate_names = {
        label.rsplit(":", maxsplit=1)[0]
        for label in bucket_avgs
        if label.endswith((":PASS", ":FAIL"))
    }
    return any(
        bucket_avgs.get(f"{gate_name}:PASS") is not None
        and bucket_avgs.get(f"{gate_name}:FAIL") is not None
        and bucket_avgs[f"{gate_name}:PASS"] > bucket_avgs[f"{gate_name}:FAIL"]
        for gate_name in gate_names
    )


def _setup_gate_fail_avg_beats_pass_avg(bucket_avgs: dict[str, float]) -> bool:
    gate_names = {
        label.rsplit(":", maxsplit=1)[0]
        for label in bucket_avgs
        if label.endswith((":PASS", ":FAIL"))
    }
    return any(
        bucket_avgs.get(f"{gate_name}:PASS") is not None
        and bucket_avgs.get(f"{gate_name}:FAIL") is not None
        and bucket_avgs[f"{gate_name}:FAIL"] > bucket_avgs[f"{gate_name}:PASS"]
        for gate_name in gate_names
    )


def _parse_evidence_bucket_avg(bucket: str) -> tuple[str, float | None]:
    parts = tuple(part.strip() for part in bucket.split("|"))
    label = parts[0] if parts else ""
    avg_part = next(
        (part for part in parts if part.startswith("avg=")),
        "",
    )
    if not avg_part:
        return label, None
    try:
        return label, float(
            avg_part.removeprefix("avg=").removesuffix("%").replace("+", "")
        )
    except ValueError:
        return label, None


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
