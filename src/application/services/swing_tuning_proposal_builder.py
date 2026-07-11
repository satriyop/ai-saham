"""Readiness planning and proposal target selection for swing tuning.

Intent:
    Deterministic, dry-run selection of tuning review targets from attribution
    evidence. Never selects parameter values, never generates YAML diffs,
    never calls AI, never mutates config.

Layer: Application
"""

from __future__ import annotations

from typing import Iterable

from src.application.services.swing_backtest_attribution import (
    SwingBacktestAttributionSummary,
)
from src.application.services.swing_tuning_contracts import (
    TuningProposalCandidate,
    TuningProposalDraft,
    TuningProposalRejection,
    TuningReadinessPlan,
)
from src.application.services.swing_tuning_evidence_strength import (
    build_tuning_evidence_by_dimension,
)

__all__ = (
    "build_tuning_readiness_plan",
    "build_tuning_proposal_draft",
    "tuning_target_scope_allowed",
)


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
        if tuning_target_scope_allowed(target.source_scope, evidence_scopes)
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

    evidence_by_dimension = build_tuning_evidence_by_dimension(summary)
    candidate_changes: list[TuningProposalCandidate] = []
    rejected_changes: list[TuningProposalRejection] = []

    for target in summary.tuning_targets:
        if not tuning_target_scope_allowed(
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


def tuning_target_scope_allowed(source_scope: str, evidence_scopes: list[str]) -> bool:
    if source_scope == "completed_trades_and_screened_candidates":
        return bool({"completed_trades", "screened_candidates"} & set(evidence_scopes))
    return source_scope in evidence_scopes


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
