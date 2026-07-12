"""Observation payload and fingerprint serialization for accumulation screening."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

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
    _candidate_observation_coverage_score,
    _strategy_evidence_fingerprint,
)

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.application.services.volatility_context import VolatilityContext
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
            "evidence_confidence": signal.evidence_confidence,
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

    return {
        "schema_version": 1,
        "artifact_type": "candidate_observation",
        "ticker": candidate.ticker,
        "snapshot_date": snapshot_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "workflow": "screen_accum",
        "screen_result": screen_result,
        "request": {
            "window_days": request.window_days,
            "min_net_buy_days": request.min_net_buy_days,
            "min_foreign_flow_score": request.min_foreign_flow_score,
            "min_signal_score": request.min_signal_score,
        },
        "sub_signal_fingerprint": sub_signal_fingerprint,
        "candidate": candidate.to_dict(),
        "signal": signal_payload,
        "trade_setup": (
            candidate.trade_setup.to_dict() if candidate.trade_setup is not None else None
        ),
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
    cq_evidence: "CompanyQualityContextEvidence | None" = None,
    setup_family_result: "PrimarySetupFamilyResult | None" = None,
    volatility_context: "VolatilityContext | None" = None,
    market_context: "MarketContext | None" = None,
) -> dict:
    """Persist raw sub-signal values as they were at observation time."""
    assessment = signal.assessment if signal is not None else None
    constraints = (
        assessment.decision_constraints.to_dict()
        if assessment is not None and assessment.decision_constraints is not None
        else {}
    )
    coverage_score = _candidate_observation_coverage_score(flow_ev=flow_ev)
    conviction_score = (
        round(signal.raw_group_score / 100.0, 4)
        if signal is not None and signal.raw_group_score is not None
        else None
    )
    flow_dict = flow_ev.to_dict() if flow_ev is not None else {}
    phase_dict = _setup_phase_fingerprint(setup_phase)
    strategy_dict = _strategy_evidence_fingerprint(strategy_evidence)
    ia_dict = _ia_evidence_fingerprint(ia_evidence)
    tp_dict = _tp_fingerprint(tp_snapshot)
    sc_dict = _sc_fingerprint(sc_evidence)
    cq_dict = _cq_fingerprint(cq_evidence)
    alpha_trigger_dict = _alpha_trigger_fingerprint(signal)
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
    return {
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
        "rs_vs_ihsg_20d_at_signal": getattr(candidate, "rs_vs_ihsg_20d", None),
        "rs_vs_ihsg_5d_at_signal": getattr(candidate, "rs_vs_ihsg_5d", None),
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
        "market_regime_at_signal": market_regime_at_signal,
        **_market_context_fingerprint(market_context),
        "decision_constraints": constraints or None,
        "coverage_score": coverage_score,
        "conviction_score": conviction_score,
    }
