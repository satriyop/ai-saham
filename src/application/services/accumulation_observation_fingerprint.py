"""Observation payload and fingerprint serialization for accumulation screening."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from src.application.dto import accumulation_screen as accumulation_dto
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
    _tp_fingerprint,
)
from src.application.services.accumulation_observation_setup_fingerprint import (
    _setup_phase_fingerprint,
)
from src.application.services.accumulation_observation_signal_fingerprint import (
    _alpha_trigger_fingerprint,
    _strategy_evidence_fingerprint,
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
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


# Config-derived request fields that make a persisted observation belong to a
# distinct scoring "version". Excludes tickers/window_days/as_of_date/regime/
# market_context — those are run-context, not config, and already have their
# own identity slots (or would make the hash churn daily without a real config
# edit). If a config knob is added to AccumulationScreenRequest, add it here so
# reruns after a config change get a distinct canonical observation.
_CONFIG_HASH_FIELDS = (
    "min_net_buy_days",
    "min_accum_score",
    "min_accum_score_enabled",
    "min_signal_score",
    "min_signal_score_enabled",
    "rsi_period",
    "sma_period",
    "resistance_gate_enabled",
    "resistance_headroom_min_pct",
    "ex_date_warning_days",
    "sector_breadth_enabled",
    "sector_breadth_threshold",
    "sector_breadth_bonus_pts",
    "sector_breadth_min_tickers",
    "bci_cluster_min_count",
    "bci_stable_min_count",
    "min_market_cap_idr",
    "min_piotroski",
    "strategy_name",
)


def compute_accumulation_config_hash(
    request: "accumulation_dto.AccumulationScreenRequest",
) -> str:
    """Fingerprint the scoring-config knobs carried on the request.

    Deterministic across runs with the same config; changes whenever a
    config-driven threshold changes, independent of which tickers/dates were
    screened.
    """
    values = {name: getattr(request, name) for name in _CONFIG_HASH_FIELDS}
    values["tier1_broker_codes"] = sorted(request.tier1_broker_codes)
    # HIGH-2: schema version is part of canonical identity — a schema-3 write
    # must never overwrite a schema-2 identity-equivalent row (or vice versa).
    values["candidate_observation_schema_version"] = CANDIDATE_OBSERVATION_SCHEMA_VERSION
    canonical = json.dumps(values, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_candidate_observation_payload(
    candidate: "accumulation_dto.AccumulationCandidate",
    *,
    screen_result: str,
    flow_ev: "FlowConfirmationEvidence | None",
    setup_phase: "SetupPhaseSnapshot | None",
    snapshot_date: date,
    captured_at: datetime,
    request: "accumulation_dto.AccumulationScreenRequest",
    strategy_evidence: "StrategyEvidence | None" = None,
    ia_evidence: "InstitutionalAccumulationEvidence | None" = None,
    tp_snapshot: "TickerProfileSnapshot | None" = None,
    sc_evidence: "SectorContextEvidence | None" = None,
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
                if signal.alpha_trigger_score is not None else None
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
        cq_evidence=cq_evidence,
        setup_family_result=setup_family_result,
        volatility_context=volatility_context,
        market_context=request.market_context,
    )

    payload = {
        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        "artifact_type": "candidate_observation",
        "ticker": candidate.ticker,
        "snapshot_date": snapshot_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "workflow": "screen_accum",
        "screen_result": screen_result,
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
    cq_dict = _cq_fingerprint(cq_evidence)
    alpha_trigger_dict = _alpha_trigger_fingerprint(signal)
    validate_current_alpha_trigger_identity(
        schema_version=CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        alpha_trigger_route_metadata=alpha_trigger_dict["alpha_trigger_route_metadata"],
    )
    volatility_dict = _volatility_fingerprint(volatility_context)
    if setup_family_result is not None:
        resolved_setup_family = (
            setup_family_result.primary_setup_family
            or constraints.get("setup_family")
        )
    else:
        resolved_setup_family = constraints.get("setup_family")
    market_regime_at_signal = (
        market_context.regime.value
        if market_context is not None
        else constraints.get("regime")
    )
    fingerprint = {
        "setup_family": resolved_setup_family,
        "matched_setup_families": (
            list(setup_family_result.matched_setup_families)
            if setup_family_result is not None
            else []
        ),
        "primary_setup_family": (
            setup_family_result.primary_setup_family
            if setup_family_result is not None
            else None
        ),
        "setup_family_source": (
            setup_family_result.setup_family_source
            if setup_family_result is not None
            else None
        ),
        "setup_family_rationale": (
            list(setup_family_result.rationale)
            if setup_family_result is not None
            else []
        ),
        "setup_name": constraints.get("setup_name"),
        **phase_dict,
        **strategy_dict,
        **ia_dict,
        **tp_dict,
        **sc_dict,
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
        "flow_component_coverage": (
            flow_ev.component_coverage if flow_ev is not None else None
        ),
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
        failed_gates = [
            gate.label for gate in gates if not getattr(gate, "passed", True)
        ]
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
