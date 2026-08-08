"""Observation payload and fingerprint serialization for accumulation screening."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Mapping

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.dto.accumulation_structural_filter import StructuralFilterDecision
from src.application.services.accumulation_observation_institutional_fingerprint import (
    _ia_evidence_fingerprint,
)
from src.application.services.accumulation_observation_metadata import (
    _market_context_fingerprint,
    _volatility_fingerprint,
)
from src.application.services.accumulation_observation_profile_fingerprint import (
    _cq_fingerprint,
    _sc_fingerprint,
    _smc_fingerprint,
    _tp_fingerprint,
)
from src.application.services.accumulation_observation_setup_fingerprint import (
    _setup_phase_fingerprint,
)
from src.application.services.accumulation_observation_signal_fingerprint import (
    _alpha_trigger_fingerprint,
    _strategy_evidence_fingerprint,
)
from src.domain.value_objects.diagnostic_producer_identity import (
    ACCUMULATION_DIAGNOSTIC_REQUIRED_PRODUCERS,
    AccumulationDiagnosticBinding,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    validate_current_alpha_trigger_identity,
    validate_current_flow_component_fingerprint,
)

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.application.services.volatility_context import VolatilityContext
    from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturn
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.institutional_accumulation_evidence import (
        InstitutionalAccumulationEvidence,
    )
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.sector_macro_context_evidence import (
        SectorMacroContextEvidence,
    )
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


# ADR-068 removed ``_CONFIG_HASH_FIELDS`` / ``compute_accumulation_config_hash``
# and the write-only ``config_hash`` payload field they populated. The request
# knobs they fingerprinted are declared-policy material, now carried by the
# ADR-059 snapshot payload digest, and scoring behaviour itself is measured by
# the behavioural probe digest — see
# ``src/application/services/behavioral_cohort_identity.py``.


def build_candidate_observation_payload(
    candidate: "accumulation_dto.AccumulationCandidate",
    *,
    screen_result: str,
    flow_ev: "FlowConfirmationEvidence | None",
    setup_phase: "SetupPhaseSnapshot | None",
    snapshot_date: date,
    captured_at: datetime,
    request: "accumulation_dto.AccumulationScreenRequest",
    structural_filter_decision: "StructuralFilterDecision",
    strategy_evidence: "StrategyEvidence | None" = None,
    ia_evidence: "InstitutionalAccumulationEvidence | None" = None,
    tp_snapshot: "TickerProfileSnapshot | None" = None,
    sc_evidence: "SectorContextEvidence | None" = None,
    smc_evidence: "SectorMacroContextEvidence | None" = None,
    cq_evidence: "CompanyQualityContextEvidence | None" = None,
    setup_family_result: "PrimarySetupFamilyResult | None" = None,
    volatility_context: "VolatilityContext | None" = None,
) -> dict:
    """Build schema-versioned replay payload for one screened candidate.

    screen_result: "pass" | "rejected_flow" | "rejected_signal"
    flow_ev: FlowConfirmationEvidence used as signal input; None if builder failed.

    Note: SignalEvidence (Phase 1 flat-factor bundle) is intentionally absent from
    the screen path. The Phase 4 staged-evidence path does not produce per-factor
    scores — building SignalEvidence from group-level breakdown would serialize
    strength=0.0 and direction=BEARISH for all present factors, which is misleading.
    flow_evidence captures the equivalent information for screen replay.
    """
    signal = candidate.signal_assessment
    signal_payload = None
    if signal is not None:
        signal_payload = {
            "assessment": signal.assessment.to_dict(),
            "coverage_warning": signal.coverage_warning,
            "signal_authority_coverage": signal.signal_authority_coverage,
            "setup_readiness": (
                signal.setup_readiness.to_dict() if signal.setup_readiness is not None else None
            ),
            "active_flags": list(signal.active_flags),
            "flag_adjustment": signal.flag_adjustment,
            "raw_group_score": signal.raw_group_score,
            "raw_exact_score": signal.raw_exact_score,
            "alpha_trigger_score": (
                signal.alpha_trigger_score.to_dict()
                if signal.alpha_trigger_score is not None
                else None
            ),
            "flow_evidence": flow_ev.to_dict() if flow_ev is not None else None,
        }

    sub_signal_fingerprint = _sub_signal_fingerprint(
        candidate=candidate,
        signal=signal,
        flow_ev=flow_ev,
        setup_phase=setup_phase,
        strategy_evidence=strategy_evidence,
        ia_evidence=ia_evidence,
        tp_snapshot=tp_snapshot,
        sc_evidence=sc_evidence,
        smc_evidence=smc_evidence,
        cq_evidence=cq_evidence,
        setup_family_result=setup_family_result,
        volatility_context=volatility_context,
        market_context=request.market_context,
    )

    payload = {
        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        "artifact_type": "candidate_observation",
        "signal_assessment_identity": (
            signal.assessment.identity.to_dict() if signal is not None else None
        ),
        "ticker": candidate.ticker,
        "snapshot_date": snapshot_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "workflow": "screen_accum",
        "screen_result": screen_result,
        "structural_filter": structural_filter_decision.to_dict(),
        "request": {
            "window_days": request.window_days,
            "min_net_buy_days": request.min_net_buy_days,
            "min_accum_score": request.min_accum_score,
            "min_signal_score": request.min_signal_score,
        },
        "sub_signal_fingerprint": sub_signal_fingerprint,
        "candidate": candidate.to_dict(),
        "signal": signal_payload,
        "trade_setup": (
            candidate.trade_setup.to_dict() if candidate.trade_setup is not None else None
        ),
    }
    return payload


def build_session_observation_payload(
    *,
    ticker: str,
    session_date: date,
    captured_at: datetime,
    canonical_window: int,
    features_by_window: dict[str, dict[str, Any]],
    shared: dict[str, Any],
    screen_results_by_window: dict[str, str] | None = None,
    population_binding: Mapping[str, Any] | None = None,
    diagnostic_bindings: Mapping[str, AccumulationDiagnosticBinding] | None = None,
) -> dict[str, Any]:
    """ADR-056: one ticker-session observation with multi-window engine packs.

    ``features_by_window`` keys are string window sizes (\"7\", \"30\", \"90\").
    Each value is a full engine pack (candidate + signal + risk + contexts).
    ``shared`` must include ``current_price`` (session close) for path labels.
    Current schema requires ``population_binding`` (Option A typed population
    authority), diagnostic bindings, and a typed structural-filter result in
    every window pack.
    """
    required = {"7", "30", "90"}
    keys = set(features_by_window)
    if keys != required:
        raise ValueError(
            f"features_by_window must have keys {sorted(required)}, got {sorted(keys)}"
        )
    raw_price = shared.get("current_price")
    try:
        price_ok = raw_price is not None and float(raw_price) > 0
    except (TypeError, ValueError):
        price_ok = False
    if not price_ok:
        raise ValueError("shared.current_price must be a positive session close")
    if population_binding is None:
        raise ValueError(
            "schema-10 session observation requires population_binding "
            "(Option A AccumPopulationBinding)"
        )
    if not isinstance(population_binding, Mapping) or not population_binding:
        raise ValueError("population_binding must be a non-empty mapping")
    if diagnostic_bindings is None:
        raise ValueError("schema-15 session observation requires diagnostic_bindings")
    if set(diagnostic_bindings) != set(ACCUMULATION_DIAGNOSTIC_REQUIRED_PRODUCERS):
        raise ValueError("diagnostic_bindings must contain the exact closed diagnostic set")
    for diagnostic_id, binding in diagnostic_bindings.items():
        if not isinstance(binding, AccumulationDiagnosticBinding):
            raise ValueError(
                f"diagnostic_bindings[{diagnostic_id!r}] must be AccumulationDiagnosticBinding"
            )
        if binding.diagnostic_id != diagnostic_id:
            raise ValueError(
                f"diagnostic binding key/id mismatch: {diagnostic_id!r} != "
                f"{binding.diagnostic_id!r}"
            )
    for window, pack in features_by_window.items():
        structural_filter = pack.get("structural_filter")
        if not isinstance(structural_filter, Mapping):
            raise ValueError(f"schema-15 features_by_window[{window!r}] requires structural_filter")
        try:
            StructuralFilterDecision.from_mapping(structural_filter)
        except ValueError as exc:
            raise ValueError(
                f"schema-15 features_by_window[{window!r}] structural_filter invalid: {exc}"
            ) from exc
    return {
        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        "artifact_type": "accumulation_session_observation",
        "ticker": ticker.upper(),
        "session_date": session_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "workflow": "research_accum_capture",
        "canonical_window": int(canonical_window),
        "horizon_primary": "accum_10d",
        "screen_results_by_window": dict(screen_results_by_window or {}),
        "shared": dict(shared),
        "population_binding": dict(population_binding),
        "diagnostic_bindings": {
            diagnostic_id: diagnostic_bindings[diagnostic_id].to_dict()
            for diagnostic_id in sorted(diagnostic_bindings)
        },
        "features_by_window": {
            "7": features_by_window["7"],
            "30": features_by_window["30"],
            "90": features_by_window["90"],
        },
    }


def _sub_signal_fingerprint(
    *,
    candidate: "accumulation_dto.AccumulationCandidate",
    signal: "AssessSignalResponse | None",
    flow_ev: "FlowConfirmationEvidence | None",
    setup_phase: "SetupPhaseSnapshot | None" = None,
    strategy_evidence: "StrategyEvidence | None" = None,
    ia_evidence: "InstitutionalAccumulationEvidence | None" = None,
    tp_snapshot: "TickerProfileSnapshot | None" = None,
    sc_evidence: "SectorContextEvidence | None" = None,
    smc_evidence: "SectorMacroContextEvidence | None" = None,
    cq_evidence: "CompanyQualityContextEvidence | None" = None,
    setup_family_result: "PrimarySetupFamilyResult | None" = None,
    volatility_context: "VolatilityContext | None" = None,
    market_context: "MarketContext | None" = None,
) -> dict:
    """Persist raw sub-signal values as they were at observation time.

    HIGH-2 schema 3: signal_authority_coverage is persisted directly from the
    assessed AssessSignalResponse — never recomputed from flow presence,
    scores, phase metrics, or Alpha/Trigger. Typed setup readiness is
    persisted as its explicit status/phase/missing-inputs/failed-requirements
    fields, not as a derived float.
    """
    assessment = signal.assessment if signal is not None else None
    constraints = (
        assessment.decision_constraints.to_dict()
        if assessment is not None and assessment.decision_constraints is not None
        else {}
    )
    signal_authority_coverage = signal.signal_authority_coverage if signal is not None else None
    readiness = signal.setup_readiness if signal is not None else None
    flow_dict = flow_ev.to_dict() if flow_ev is not None else {}
    phase_dict = _setup_phase_fingerprint(setup_phase)
    strategy_dict = _strategy_evidence_fingerprint(strategy_evidence)
    ia_dict = _ia_evidence_fingerprint(ia_evidence)
    tp_dict = _tp_fingerprint(tp_snapshot)
    sc_dict = _sc_fingerprint(sc_evidence)
    smc_dict = _smc_fingerprint(smc_evidence)
    cq_dict = _cq_fingerprint(cq_evidence)
    alpha_trigger_dict = _alpha_trigger_fingerprint(signal)
    validate_current_alpha_trigger_identity(
        schema_version=CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        alpha_trigger_route_metadata=alpha_trigger_dict["alpha_trigger_route_metadata"],
    )
    volatility_dict = _volatility_fingerprint(volatility_context)
    if setup_family_result is not None:
        resolved_setup_family = setup_family_result.primary_setup_family or constraints.get(
            "setup_family"
        )
    else:
        resolved_setup_family = constraints.get("setup_family")
    market_regime_at_signal = (
        market_context.regime.value if market_context is not None else constraints.get("regime")
    )
    fingerprint = {
        "signal_assessment_identity": (
            assessment.identity.to_dict() if assessment is not None else None
        ),
        "setup_family": resolved_setup_family,
        "matched_setup_families": (
            list(setup_family_result.matched_setup_families)
            if setup_family_result is not None
            else []
        ),
        "primary_setup_family": (
            setup_family_result.primary_setup_family if setup_family_result is not None else None
        ),
        "setup_family_source": (
            setup_family_result.setup_family_source if setup_family_result is not None else None
        ),
        "setup_family_rationale": (
            list(setup_family_result.rationale) if setup_family_result is not None else []
        ),
        "setup_name": constraints.get("setup_name"),
        **phase_dict,
        **strategy_dict,
        **ia_dict,
        **tp_dict,
        **sc_dict,
        **smc_dict,
        **cq_dict,
        **alpha_trigger_dict,
        **volatility_dict,
        "rsi_at_signal": candidate.rsi,
        "bb_width_pctile_at_signal": candidate.bb_width_pctile,
        "vwap_position_at_signal": candidate.vwap_pct,
        "benchmark_excess_return_5_session": _benchmark_excess_return_dict(
            getattr(candidate, "benchmark_excess_return_5_session", None)
        ),
        "benchmark_excess_return_20_session": _benchmark_excess_return_dict(
            getattr(candidate, "benchmark_excess_return_20_session", None)
        ),
        "benchmark_excess_return_authority_status": "DIAGNOSTIC_UNVALIDATED",
        "volume_ratio_at_signal": candidate.avg_flow_ratio,
        "cnfb_20d_at_signal": float(candidate.total_net_value),
        "foreign_participation_at_signal": candidate.net_buy_ratio,
        "foreign_concentration_at_signal": flow_dict.get("capped_strength"),
        "domestic_broker_accumulation_at_signal": (
            candidate.bandar_detector.bandar_score
            if candidate.bandar_detector is not None
            and hasattr(candidate.bandar_detector, "bandar_score")
            else None
        ),
        "flow_component_coverage": (flow_ev.component_coverage if flow_ev is not None else None),
        "flow_missing_components": (
            list(flow_ev.missing_components) if flow_ev is not None else []
        ),
        "market_regime_at_signal": market_regime_at_signal,
        **_market_context_fingerprint(market_context),
        "decision_constraints": constraints or None,
        "signal_authority_coverage": signal_authority_coverage,
        "setup_readiness_status": readiness.status.value if readiness is not None else None,
        "setup_readiness_current_phase": (
            readiness.current_phase.value
            if readiness is not None and readiness.current_phase is not None
            else None
        ),
        "setup_readiness_missing_required_inputs": (
            list(readiness.missing_required_inputs) if readiness is not None else []
        ),
        "setup_readiness_failed_requirements": (
            list(readiness.failed_requirements) if readiness is not None else []
        ),
        "named_setup_evaluations": _named_setup_evaluations_fingerprint(
            getattr(candidate, "named_setup_evaluations", None)
        ),
    }
    validate_current_flow_component_fingerprint(
        schema_version=CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        fingerprint=fingerprint,
    )
    return fingerprint


# Diagnostic strength mapping mirrors SetupEvidenceBuilder — research/audit only.
_NAMED_SETUP_MATCH_STRENGTH: dict[str, float] = {
    "MATCH": 100.0,
    "PARTIAL": 60.0,
    "NO_MATCH": 20.0,
}


def _named_setup_evaluations_fingerprint(
    evaluations: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Lean per-setup match snapshot for schema-v8 research/audit.

    Does not change ENTER/authority. Keys are setup names from
    AVAILABLE_SWING_SETUPS. failed_gates lists labels of gates that did not
    pass (empty on MATCH).
    """
    if not evaluations:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for setup_name in sorted(evaluations):
        evaluation = evaluations[setup_name]
        match_value = getattr(getattr(evaluation, "match", None), "value", None)
        if match_value is None:
            match_value = str(getattr(evaluation, "match", "NO_MATCH"))
        gates = getattr(evaluation, "gates", ()) or ()
        failed_gates = [gate.label for gate in gates if not getattr(gate, "passed", True)]
        out[setup_name] = {
            "match": match_value,
            "failed_gates": failed_gates,
            "match_strength": _NAMED_SETUP_MATCH_STRENGTH.get(match_value, 20.0),
            "family": getattr(evaluation, "family", "unknown"),
            "entry_authority": bool(getattr(evaluation, "entry_authority", True)),
        }
    return out


def _benchmark_excess_return_dict(
    window: "BenchmarkExcessReturn | None",
) -> dict | None:
    return window.to_dict() if window is not None else None
