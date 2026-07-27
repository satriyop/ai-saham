"""
SignalEvidenceGroupScorer — handles setup/flow scoring, renormalization, flags, and classification.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.value_objects.alpha_trigger_score import EvidenceAuthorityStatus
from src.domain.value_objects.evidence_source_availability import (
    AuthorityDenominatorScope,
)
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalStrength,
)

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalEvidenceRequest
    from src.application.services.signal_engine_config import (
        EvidenceGroupConfig,
        SignalEngineConfig,
    )
    from src.domain.value_objects.canonical_signal_evidence_input import (
        FlowEvidenceGroupInput,
        SetupEvidenceGroupInput,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.signal_assessment import SignalContext


@dataclass(frozen=True)
class _GroupAuthorityFacts:
    """Typed per-group authority facts (HIGH-2) — the single source both
    signal_authority_coverage computation and coverage-warning generation
    read from, so they can never disagree."""

    name: str
    weight: float
    required: bool
    is_production: bool
    present: bool
    authoritative: bool
    # Fraction of group weight that is both source-authoritative and
    # component-complete. Setup remains 1.0/0.0; flow multiplies source
    # authority by flow.component_coverage.
    authority_fraction: float
    # True when a real consumed contributor was left unassessed (e.g. bandar).
    # Blocks complete-authority claims without necessarily zeroing
    # settled_authority_fraction.
    has_unassessed_contributors: bool = False


@dataclass(frozen=True)
class SignalEvidenceGroupScores:
    setup_group_score: float
    setup_present: bool
    flow_group_score: float
    flow_present: bool
    base_score: float
    # Canonical production-authority coverage (HIGH-2): weighted fraction of
    # required PRODUCTION evidence groups that are both present and
    # source-authoritative. NOT statistical confidence or trade conviction.
    signal_authority_coverage: float
    active_flags: tuple[str, ...]
    flag_adjustment: int
    raw_exact_score: float
    raw_group_score: int
    final_score: int
    strength: SignalStrength
    entry_quality: EntryQuality
    gate_tightened: bool
    coverage_warning: str | None


class SignalEvidenceGroupScorer:
    @staticmethod
    def score(
        request: AssessSignalEvidenceRequest,
        config: SignalEngineConfig,
    ) -> SignalEvidenceGroupScores:
        setup_group_score, setup_present = SignalEvidenceGroupScorer._score_setup_group(
            request.setup_evidence
        )
        flow_group_score, flow_present = SignalEvidenceGroupScorer._score_flow_group(
            request.flow_confirmation_evidence
        )

        base_score, _presence_ratio = SignalEvidenceGroupScorer.renormalize(
            setup_group_score, setup_present, flow_group_score, flow_present, config
        )

        group_authority_facts = SignalEvidenceGroupScorer._group_authority_facts(
            request, setup_present, flow_present, config
        )
        signal_authority_coverage = SignalEvidenceGroupScorer._compute_signal_authority_coverage(
            group_authority_facts,
            scope=request.authority_denominator_scope,
        )

        active_flags, flag_adjustment = SignalEvidenceGroupScorer._evaluate_flags(
            request.signal_context, config
        )

        raw_exact_score = max(0.0, min(100.0, base_score + flag_adjustment))
        raw_group_score = round(base_score)
        final_score = max(0, min(100, raw_group_score + flag_adjustment))

        strength = SignalEvidenceGroupScorer._classify_strength(final_score, config)
        entry_quality = SignalEvidenceGroupScorer._classify_entry(strength, config)

        entry_quality, gate_tightened = SignalEvidenceGroupScorer._apply_gate_tightening(
            entry_quality, request.market_context
        )

        coverage_warning = SignalEvidenceGroupScorer._coverage_warning(
            group_authority_facts,
            flow_evidence=request.flow_confirmation_evidence,
            scope=request.authority_denominator_scope,
        )

        return SignalEvidenceGroupScores(
            setup_group_score=setup_group_score,
            setup_present=setup_present,
            flow_group_score=flow_group_score,
            flow_present=flow_present,
            base_score=base_score,
            signal_authority_coverage=signal_authority_coverage,
            active_flags=tuple(active_flags),
            flag_adjustment=flag_adjustment,
            raw_exact_score=raw_exact_score,
            raw_group_score=raw_group_score,
            final_score=final_score,
            strength=strength,
            entry_quality=entry_quality,
            gate_tightened=gate_tightened,
            coverage_warning=coverage_warning,
        )

    @staticmethod
    def _score_setup_group(ev: SetupEvidence | None) -> tuple[float, bool]:
        if ev is None:
            return 0.0, False
        return float(ev.match_strength), True

    @staticmethod
    def _score_flow_group(ev: FlowConfirmationEvidence | None) -> tuple[float, bool]:
        if ev is None:
            return 0.0, False
        return max(0.0, min(100.0, ev.capped_strength * 100.0)), True

    @staticmethod
    def renormalize(
        setup_group_score: float,
        setup_present: bool,
        flow_group_score: float,
        flow_present: bool,
        config: SignalEngineConfig,
    ) -> tuple[float, float]:
        """Compute directional base score and raw group-presence ratio.

        base_score is a weighted average of present groups' scores; missing
        groups are excluded from the denominator (never neutral-filled). The
        second returned value is a raw presence ratio — NOT
        signal_authority_coverage. It exists only for internal call-signature
        compatibility with SignalLegacyRegimeConditioning's diagnostic path.
        Production-authority coverage is computed separately by
        `_compute_signal_authority_coverage`, since directional score
        arithmetic must remain based on attached evidence exactly as today
        while authority coverage additionally requires PRODUCTION
        registration and source availability.
        """
        g = config.evidence_groups
        total_weight = g.setup_quality.weight + g.flow_confirmation.weight

        active: list[tuple[float, float]] = []  # (score, weight)
        if setup_present:
            active.append((setup_group_score, g.setup_quality.weight))
        if flow_present:
            active.append((flow_group_score, g.flow_confirmation.weight))

        if not active:
            return 50.0, 0.0

        present_weight = sum(w for _, w in active)
        base_score = sum(s * w for s, w in active) / present_weight
        presence_ratio = min(1.0, present_weight / total_weight) if total_weight > 0 else 0.0
        return base_score, presence_ratio

    @staticmethod
    def _is_production_registered(
        group_config: EvidenceGroupConfig,
        config: SignalEngineConfig,
    ) -> bool:
        """Unknown registration resolves as diagnostic (HIGH-2)."""
        registration = config.alpha_trigger.evidence_registrations.get(
            group_config.authority_registration
        )
        if registration is None:
            return False
        return registration.status == EvidenceAuthorityStatus.PRODUCTION

    @staticmethod
    def _group_authoritative_present(
        group_input: "SetupEvidenceGroupInput | FlowEvidenceGroupInput | None",
    ) -> bool:
        return group_input is not None and group_input.availability.all_authoritative

    @staticmethod
    def _source_authority_fraction(
        group_input: "SetupEvidenceGroupInput | FlowEvidenceGroupInput | None",
    ) -> float:
        if group_input is None:
            return 0.0
        # Settled families only — unassessed contributors block
        # all_authoritative but must not zero coverage for CURRENT brokers.
        return group_input.availability.settled_authority_fraction

    @staticmethod
    def _has_unassessed_contributors(
        group_input: "SetupEvidenceGroupInput | FlowEvidenceGroupInput | None",
    ) -> bool:
        if group_input is None:
            return False
        return bool(group_input.availability.unassessed_contributors)

    @staticmethod
    def _flow_component_coverage(
        flow_ev: "FlowConfirmationEvidence | None",
    ) -> float:
        if flow_ev is None:
            return 0.0
        return max(0.0, min(1.0, float(flow_ev.component_coverage)))

    @staticmethod
    def _group_authority_facts(
        request: AssessSignalEvidenceRequest,
        setup_present: bool,
        flow_present: bool,
        config: SignalEngineConfig,
    ) -> tuple[_GroupAuthorityFacts, ...]:
        """Single source of truth for per-group authority facts, consumed by
        both `_compute_signal_authority_coverage` and `_coverage_warning` so
        the two can never disagree about what is present/registered/
        authoritative for a given assessment."""
        g = config.evidence_groups
        canonical_evidence = request.canonical_evidence
        setup_group_input = canonical_evidence.setup if canonical_evidence else None
        flow_group_input = canonical_evidence.flow if canonical_evidence else None
        setup_source_auth = SignalEvidenceGroupScorer._source_authority_fraction(setup_group_input)
        flow_source_auth = SignalEvidenceGroupScorer._source_authority_fraction(flow_group_input)
        flow_component_coverage = SignalEvidenceGroupScorer._flow_component_coverage(
            request.flow_confirmation_evidence
        )
        setup_auth = setup_present and setup_source_auth > 0.0
        flow_auth = flow_present and flow_source_auth > 0.0
        return (
            _GroupAuthorityFacts(
                name="setup_quality",
                weight=g.setup_quality.weight,
                required=g.setup_quality.required_for_authority,
                is_production=SignalEvidenceGroupScorer._is_production_registered(
                    g.setup_quality, config
                ),
                present=setup_present,
                authoritative=setup_auth,
                # Setup remains source-authoritative 1.0 or 0.0.
                authority_fraction=(setup_source_auth if setup_present else 0.0),
                has_unassessed_contributors=(
                    SignalEvidenceGroupScorer._has_unassessed_contributors(setup_group_input)
                ),
            ),
            _GroupAuthorityFacts(
                name="flow_confirmation",
                weight=g.flow_confirmation.weight,
                required=g.flow_confirmation.required_for_authority,
                is_production=SignalEvidenceGroupScorer._is_production_registered(
                    g.flow_confirmation, config
                ),
                present=flow_present,
                authoritative=flow_auth and flow_component_coverage > 0.0,
                # flow authority = source_authoritative_fraction * component_coverage
                authority_fraction=(
                    flow_source_auth * flow_component_coverage if flow_present else 0.0
                ),
                has_unassessed_contributors=(
                    SignalEvidenceGroupScorer._has_unassessed_contributors(flow_group_input)
                ),
            ),
        )

    @staticmethod
    def _compute_signal_authority_coverage(
        facts: tuple[_GroupAuthorityFacts, ...],
        *,
        scope: AuthorityDenominatorScope = AuthorityDenominatorScope.ALL_REQUIRED,
    ) -> float:
        """signal_authority_coverage = weighted authority_fraction of required
        PRODUCTION groups / required PRODUCTION weight (HIGH-2 + DQ-001).

        DIAGNOSTIC/LOW_WEIGHT groups never enter the numerator or denominator.

        ALL_REQUIRED (default / swing): a required PRODUCTION group stays in
        the denominator even when absent or unavailable — it is never
        renormalized away.

        ATTACHED_REQUIRED (screen discovery): only required PRODUCTION groups
        attached on this request enter the denominator. Intentionally
        unattached groups are out of scope for this assessment.

        Flow contributes proportionally via component_coverage; setup remains
        binary. Directional base_score is unchanged by authority arithmetic.
        """
        denominator = 0.0
        numerator = 0.0
        for fact in facts:
            if not (fact.is_production and fact.required):
                continue
            if scope is AuthorityDenominatorScope.ATTACHED_REQUIRED and not fact.present:
                continue
            denominator += fact.weight
            numerator += fact.weight * max(0.0, min(1.0, fact.authority_fraction))

        if denominator <= 0:
            return 0.0
        return min(1.0, numerator / denominator)

    @staticmethod
    def _evaluate_flags(
        ctx: SignalContext | None,
        config: SignalEngineConfig,
    ) -> tuple[list[str], int]:
        if ctx is None:
            return [], 0

        flags_cfg = config.flags
        active: list[str] = []
        total_penalty = 0

        if (
            flags_cfg.valuation_stretched.enabled
            and ctx.forward_pe is not None
            and ctx.forward_pe > flags_cfg.valuation_stretched.forward_pe_threshold
        ):
            active.append("VALUATION_STRETCHED")
            total_penalty -= flags_cfg.valuation_stretched.score_penalty

        if (
            flags_cfg.analyst_bearish.enabled
            and ctx.analyst_buy_pct is not None
            and ctx.analyst_buy_pct < flags_cfg.analyst_bearish.buy_ratio_threshold
        ):
            active.append("ANALYST_BEARISH")
            total_penalty -= flags_cfg.analyst_bearish.score_penalty

        if (
            flags_cfg.insider_selling.enabled
            and ctx.insider_net_buy_ratio is not None
            and ctx.insider_net_buy_ratio < flags_cfg.insider_selling.net_buy_ratio_threshold
        ):
            active.append("INSIDER_SELLING")
            total_penalty -= flags_cfg.insider_selling.score_penalty

        return active, total_penalty

    @staticmethod
    def _classify_strength(score: int, config: SignalEngineConfig) -> SignalStrength:
        cfg = config.classification
        if score >= cfg.strong_min_score:
            return SignalStrength.STRONG
        if score >= cfg.moderate_min_score:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    @staticmethod
    def _classify_entry(strength: SignalStrength, config: SignalEngineConfig) -> EntryQuality:
        """Directional strength only (HIGH-2). Authority coverage is applied
        exactly once, downstream, by DecisionPolicyService — never here."""
        del config  # kept for call-signature stability; no thresholds remain
        if strength == SignalStrength.STRONG:
            return EntryQuality.ENTER
        if strength == SignalStrength.MODERATE:
            return EntryQuality.WATCH
        return EntryQuality.AVOID

    @staticmethod
    def _apply_gate_tightening(
        entry_quality: EntryQuality,
        market_context: MarketContext | None,
    ) -> tuple[EntryQuality, bool]:
        if (
            market_context is not None
            and market_context.gate_tightening
            and entry_quality == EntryQuality.ENTER
        ):
            return EntryQuality.WATCH, True
        return entry_quality, False

    @staticmethod
    def _coverage_warning(
        facts: tuple[_GroupAuthorityFacts, ...],
        *,
        flow_evidence: "FlowConfirmationEvidence | None" = None,
        scope: AuthorityDenominatorScope = AuthorityDenominatorScope.ALL_REQUIRED,
    ) -> str | None:
        """HIGH-2 + DQ-001: distinguish exactly why authority coverage is incomplete.

        1. No setup or flow evidence attached at all — reported once, no
           per-group detail needed.
        2. Evidence attached but its registration is not PRODUCTION —
           diagnostic/low-weight evidence never raises authority coverage.
        3. Evidence attached and PRODUCTION-registered but its resolved
           source availability is not authoritative — names the group.
        4. Required PRODUCTION evidence absent — names the group
           (ALL_REQUIRED scope only; ATTACHED_REQUIRED skips intentionally
           unattached groups).
        5. Flow present with partial component coverage — names missing
           flow components.
        6. Settled sources authoritative but unassessed contributors present
           — complete-authority claim unavailable (e.g. bandar_detector).

        Never renders an empty "missing:" list, and never uses the phrases
        "evidence confidence" or "conviction".
        """
        if not any(fact.present for fact in facts):
            return "No evidence groups present — score is neutral prior only"

        problems: list[str] = []
        for fact in facts:
            if not (fact.required and fact.is_production):
                if fact.present:
                    problems.append(
                        f"{fact.name}: attached but registration is not PRODUCTION "
                        "(diagnostic/low-weight evidence cannot raise authority coverage)"
                    )
                continue
            if not fact.present:
                if scope is AuthorityDenominatorScope.ATTACHED_REQUIRED:
                    continue
                problems.append(f"{fact.name}: required evidence absent")
            elif fact.authority_fraction <= 0.0:
                problems.append(f"{fact.name}: present but not source-authoritative")
            elif fact.authority_fraction < 1.0:
                if (
                    fact.name == "flow_confirmation"
                    and flow_evidence is not None
                    and flow_evidence.missing_components
                ):
                    missing = ", ".join(flow_evidence.missing_components)
                    problems.append(f"{fact.name}: missing components: {missing}")
                else:
                    problems.append(
                        f"{fact.name}: partial authority "
                        f"(authority_fraction={fact.authority_fraction:.4f})"
                    )
            if fact.present and fact.has_unassessed_contributors and fact.authority_fraction > 0.0:
                problems.append(
                    f"{fact.name}: settled sources authoritative but "
                    "unassessed contributors prevent complete-authority claim"
                )

        if not problems:
            return None
        return "Incomplete signal authority coverage — " + "; ".join(problems)
