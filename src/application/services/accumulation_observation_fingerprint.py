"""Observation payload and fingerprint serialization for accumulation screening."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from src.application.dto import accumulation_screen as accumulation_dto

if TYPE_CHECKING:
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.application.services.volatility_context import VolatilityContext
    from src.application.dto.assess_signal import AssessSignalResponse
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


def _market_context_fingerprint(market_context: "MarketContext | None") -> dict:
    """Persist full regime attribution from a supplied MarketContext, else None."""
    return {
        "regime_confidence_at_signal": (
            market_context.regime_confidence if market_context is not None else None
        ),
        "regime_stability_at_signal": (
            market_context.regime_stability if market_context is not None else None
        ),
        "days_in_regime_at_signal": (
            market_context.days_in_regime if market_context is not None else None
        ),
        "regime_transition_warning_at_signal": (
            market_context.transition_warning if market_context is not None else None
        ),
        # MarketContext exposes no detection-method field anywhere in the codebase
        # (verified: zero hits for regime_detection_method/detection_method/regime_source).
        "regime_detection_method_at_signal": None,
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
        # Prefer the resolver's primary family; fall back to
        # decision_constraints only when the resolver itself came back
        # unresolved (e.g. fallback_unknown), so a real constraints-sourced
        # family is never silently discarded.
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


def _alpha_trigger_fingerprint(signal: "AssessSignalResponse | None") -> dict:
    score = signal.alpha_trigger_score if signal is not None else None
    if score is None:
        return {
            "alpha_score": None,
            "trigger_score": None,
            "alpha_trigger_final_exact_score": None,
            "alpha_trigger_horizon": None,
            "alpha_trigger_alpha_weight": None,
            "flow_trigger_allowed": None,
            "alpha_trigger_route_metadata": None,
            "alpha_trigger_unavailable_reasons": [],
        }
    return {
        "alpha_score": score.alpha_score,
        "trigger_score": score.trigger_score,
        "alpha_trigger_final_exact_score": score.final_exact_score,
        "alpha_trigger_horizon": score.horizon,
        "alpha_trigger_alpha_weight": score.alpha_weight,
        "flow_trigger_allowed": score.flow_trigger_allowed,
        "alpha_trigger_route_metadata": [
            contribution.to_dict()
            for contribution in score.group_contributions
        ],
        "alpha_trigger_unavailable_reasons": list(score.unavailable_reasons),
    }


def _setup_phase_fingerprint(
    setup_phase: "SetupPhaseSnapshot | None",
) -> dict:
    if setup_phase is None:
        return {
            "setup_phase_current": None,
            "setup_phase_previous": None,
            "phase_sequence_valid": None,
            "phase_age_sessions": None,
            "phase_strength": None,
            "phase_reasons": [],
            "phase_history": [],
            "phase_coverage_score": None,
            "phase_conviction_score": None,
            "volume_dry_up_ratio_at_signal": None,
            "volume_expansion_ratio_at_signal": None,
            "volume_dry_up_confirmed": None,
            "volume_expansion_confirmed": None,
            "volume_trigger_confirmed": None,
        }
    return {
        "setup_phase_current": setup_phase.current_phase.value,
        "setup_phase_previous": (
            setup_phase.previous_phase.value if setup_phase.previous_phase else None
        ),
        "phase_sequence_valid": setup_phase.sequence_valid,
        "phase_age_sessions": setup_phase.phase_age_sessions,
        "phase_strength": setup_phase.phase_strength,
        "phase_reasons": list(setup_phase.reasons),
        "phase_history": [entry.to_dict() for entry in setup_phase.history],
        "phase_coverage_score": setup_phase.coverage_score,
        "phase_conviction_score": setup_phase.conviction_score,
        "volume_dry_up_ratio_at_signal": setup_phase.volume_dry_up_ratio,
        "volume_expansion_ratio_at_signal": setup_phase.volume_expansion_ratio,
        "volume_dry_up_confirmed": setup_phase.volume_dry_up_confirmed,
        "volume_expansion_confirmed": setup_phase.volume_expansion_confirmed,
        "volume_trigger_confirmed": setup_phase.volume_trigger_confirmed,
    }


def _ia_evidence_fingerprint(
    ia_evidence: "InstitutionalAccumulationEvidence | None",
) -> dict:
    _none: dict = {
        "institutional_accumulation_status": None,
        "ia_foreign_participation": None,
        "ia_foreign_cr4": None,
        "ia_foreign_cr8": None,
        "ia_cnfb_divergence_20d": None,
        "ia_cnfb_divergence_30d": None,
        "ia_cnfb_distribution_3d": None,
        "ia_foreign_vwap_distance": None,
        "ia_foreign_track_coverage": None,
        "ia_foreign_track_conviction": None,
        "ia_domestic_broker_consistency": None,
        "ia_domestic_broker_reversal": None,
        "ia_domestic_accumulation_session_ratio": None,
        "ia_domestic_buy_vwap_distance": None,
        "ia_domestic_broker_hhi_divergence": None,
        "ia_bandar_broad_score_normalized": None,
        "ia_domestic_track_coverage": None,
        "ia_domestic_track_conviction": None,
        "ia_counterparty_transfer_asymmetry": None,
        "ia_counterparty_buy_hhi": None,
        "ia_counterparty_sell_hhi": None,
        "ia_coverage_score": None,
        "ia_conviction_score": None,
    }
    if ia_evidence is None:
        return _none
    ft = ia_evidence.foreign_institutional_track
    dt = ia_evidence.domestic_bandar_track
    ct = ia_evidence.counterparty_transfer
    meta = ia_evidence.metadata or {}
    bullish = meta.get("cnfb_bullish_scores") or {}
    bearish = meta.get("cnfb_bearish_scores") or {}
    return {
        "institutional_accumulation_status": ia_evidence.evidence_status.value,
        "ia_foreign_participation": ft.foreign_participation_score,
        "ia_foreign_cr4": ft.foreign_cr4_score,
        "ia_foreign_cr8": ft.foreign_cr8_score,
        "ia_cnfb_divergence_20d": bullish.get("cnfb_20d"),
        "ia_cnfb_divergence_30d": bullish.get("cnfb_30d"),
        "ia_cnfb_distribution_3d": bearish.get("cnfb_3d"),
        "ia_foreign_vwap_distance": ft.foreign_vwap_distance_score,
        "ia_foreign_track_coverage": ft.coverage_score,
        "ia_foreign_track_conviction": ft.conviction_score,
        "ia_domestic_broker_consistency": dt.broker_consistency_score,
        "ia_domestic_broker_reversal": dt.broker_reversal_score,
        "ia_domestic_accumulation_session_ratio": dt.accumulation_session_ratio,
        "ia_domestic_buy_vwap_distance": dt.domestic_buy_vwap_distance_score,
        "ia_domestic_broker_hhi_divergence": dt.broker_hhi_divergence_score,
        "ia_bandar_broad_score_normalized": dt.bandar_broad_score_normalized,
        "ia_domestic_track_coverage": dt.coverage_score,
        "ia_domestic_track_conviction": dt.conviction_score,
        "ia_counterparty_transfer_asymmetry": ct.transfer_asymmetry_score if ct else None,
        "ia_counterparty_buy_hhi": ct.buy_side_hhi if ct else None,
        "ia_counterparty_sell_hhi": ct.sell_side_hhi if ct else None,
        "ia_coverage_score": ia_evidence.coverage_score,
        "ia_conviction_score": ia_evidence.conviction_score,
    }


def _tp_fingerprint(
    tp: "TickerProfileSnapshot | None",
) -> dict:
    _none: dict = {
        "ticker_profile_label": None,
        "ticker_profile_confidence": None,
        "tp_market_tier": None,
        "tp_foreign_institutional_exposure": None,
        "tp_domestic_bandar_exposure": None,
        "tp_retail_speculative_exposure": None,
        "tp_liquidity_score": None,
        "tp_broker_concentration_score": None,
        "tp_foreign_flow_score": None,
        "tp_volatility_score": None,
        "tp_index_membership_score": None,
        "tp_market_cap_bucket": None,
        "tp_sector": None,
        "tp_index_memberships": None,
        "tp_coverage_score": None,
        "tp_epoch": None,
    }
    if tp is None:
        return _none
    return {
        "ticker_profile_label": tp.primary_profile,
        "ticker_profile_confidence": tp.profile_confidence,
        "tp_market_tier": tp.market_tier,
        "tp_foreign_institutional_exposure": tp.foreign_institutional_exposure,
        "tp_domestic_bandar_exposure": tp.domestic_bandar_exposure,
        "tp_retail_speculative_exposure": tp.retail_speculative_exposure,
        "tp_liquidity_score": tp.liquidity_score,
        "tp_broker_concentration_score": tp.broker_concentration_score,
        "tp_foreign_flow_score": tp.foreign_flow_score,
        "tp_volatility_score": tp.volatility_score,
        "tp_index_membership_score": tp.index_membership_score,
        "tp_market_cap_bucket": tp.market_cap_bucket or "UNKNOWN",
        "tp_sector": tp.sector,
        "tp_index_memberships": ",".join(tp.index_memberships) if tp.index_memberships else None,
        "tp_coverage_score": tp.coverage_score,
        "tp_epoch": tp.epoch,
    }


def _volatility_fingerprint(vc: "VolatilityContext | None") -> dict:
    if vc is None:
        return {
            "atr_at_signal": None,
            "atr_pct_at_signal": None,
            "volatility_bucket_at_signal": None,
            "volatility_size_multiplier_at_signal": None,
        }
    return {
        "atr_at_signal": vc.atr_at_signal,
        "atr_pct_at_signal": vc.atr_pct_at_signal,
        "volatility_bucket_at_signal": vc.volatility_bucket_at_signal,
        "volatility_size_multiplier_at_signal": vc.volatility_size_multiplier_at_signal,
    }


def _sc_fingerprint(
    sc: "SectorContextEvidence | None",
) -> dict:
    _none: dict = {
        "sc_sector": None,
        "sc_peer_count": None,
        "sc_sector_20d_return": None,
        "sc_sector_vs_ihsg_20d": None,
        "sc_sector_breadth": None,
        "sc_ticker_vs_sector_rs": None,
        "sc_sector_regime": None,
        "sc_coverage_score": None,
    }
    if sc is None:
        return _none
    return {
        "sc_sector": sc.sector,
        "sc_peer_count": sc.peer_count,
        "sc_sector_20d_return": sc.sector_20d_return,
        "sc_sector_vs_ihsg_20d": sc.sector_vs_ihsg_20d,
        "sc_sector_breadth": sc.sector_breadth,
        "sc_ticker_vs_sector_rs": sc.ticker_vs_sector_rs,
        "sc_sector_regime": sc.sector_regime,
        "sc_coverage_score": sc.coverage_score,
    }


def _cq_fingerprint(
    cq: "CompanyQualityContextEvidence | None",
) -> dict:
    _none: dict = {
        "cq_valuation_score": None,
        "cq_earnings_trend_score": None,
        "cq_analyst_score": None,
        "cq_insider_score": None,
        "cq_seasonality_score": None,
        "cq_aggregate_score": None,
        "cq_coverage_score": None,
        "cq_present_axis_count": None,
    }
    if cq is None:
        return _none
    return {
        "cq_valuation_score": cq.valuation_score,
        "cq_earnings_trend_score": cq.earnings_trend_score,
        "cq_analyst_score": cq.analyst_score,
        "cq_insider_score": cq.insider_score,
        "cq_seasonality_score": cq.seasonality_score,
        "cq_aggregate_score": cq.aggregate_score,
        "cq_coverage_score": cq.coverage_score,
        "cq_present_axis_count": len(cq.present_axes),
    }


def _strategy_evidence_fingerprint(
    strategy_evidence: "StrategyEvidence | None",
) -> dict:
    if strategy_evidence is None:
        return {
            "strategy_name": None,
            "strategy_rule_name": None,
            "strategy_rule_outcome": None,
            "strategy_evidence_route": None,
            "strategy_evidence_outcome": None,
            "strategy_coverage_score": None,
            "strategy_conviction_score": None,
            "strategy_freshness_score": None,
            "strategy_rationale": [],
        }
    matched = strategy_evidence.matched_rule
    return {
        "strategy_name": strategy_evidence.strategy_name,
        "strategy_rule_name": matched.rule_name if matched else None,
        "strategy_rule_outcome": matched.rule_outcome if matched else None,
        "strategy_evidence_route": matched.evidence_route if matched else None,
        "strategy_evidence_outcome": strategy_evidence.outcome.value,
        "strategy_coverage_score": strategy_evidence.coverage_score,
        "strategy_conviction_score": strategy_evidence.conviction_score,
        "strategy_freshness_score": strategy_evidence.freshness_score,
        "strategy_rationale": list(strategy_evidence.rationale),
    }


def _candidate_observation_coverage_score(
    *,
    flow_ev: "FlowConfirmationEvidence | None",
) -> float:
    # Phase B has no SetupPhaseState/setup evidence in screen observations yet.
    # Persist availability ratio, not directional strength.
    present_groups = 1 if flow_ev is not None else 0
    return round(present_groups / 2.0, 4)
