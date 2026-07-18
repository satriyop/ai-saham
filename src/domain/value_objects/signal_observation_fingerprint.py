"""Signal observation fingerprint for signal-time fact preservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturn
from src.domain.value_objects.signal_observation_fingerprint_serialization import (
    signal_observation_fingerprint_from_dict,
    signal_observation_fingerprint_to_dict,
)


@dataclass(frozen=True)
class SignalObservationFingerprint:
    """Raw signal-time facts persisted for later attribution."""

    setup_family: str | None = None
    matched_setup_families: tuple[str, ...] = ()
    primary_setup_family: str | None = None
    setup_family_source: str | None = None
    setup_family_rationale: tuple[str, ...] = ()
    setup_name: str | None = None
    setup_phase: str | None = None
    setup_phase_previous: str | None = None
    phase_sequence_valid: bool | None = None
    phase_age_sessions: int | None = None
    # Legacy (schema 1/2) diagnostic-only fields — populated only when the
    # source row actually used these ambiguous names. Never fabricated from
    # phase_detection_strength/phase_input_coverage below.
    phase_strength: float | None = None
    phase_coverage_score: float | None = None
    phase_conviction_score: float | None = None
    phase_reasons: tuple[str, ...] = ()
    phase_history: tuple[dict[str, Any], ...] = ()
    # HIGH-2 canonical (schema 3) truthfully-named diagnostic phase metrics.
    phase_detection_strength: float | None = None
    phase_input_coverage: float | None = None
    strategy_name: str | None = None
    strategy_rule_name: str | None = None
    strategy_rule_outcome: str | None = None
    strategy_evidence_route: str | None = None
    strategy_evidence_outcome: str | None = None
    strategy_coverage_score: float | None = None
    strategy_conviction_score: float | None = None
    strategy_freshness_score: float | None = None
    strategy_rationale: tuple[str, ...] = ()
    rsi: float | None = None
    bb_width_pctile: float | None = None
    vwap_position: float | None = None
    volume_ratio: float | None = None
    # Explicit dry-up/expansion evidence (Point 3, docs/signal_refactor.md)
    volume_dry_up_ratio: float | None = None
    volume_expansion_ratio: float | None = None
    volume_dry_up_confirmed: bool | None = None
    volume_expansion_confirmed: bool | None = None
    volume_trigger_confirmed: bool | None = None
    cnfb: float | None = None
    foreign_participation: float | None = None
    foreign_concentration: float | None = None
    domestic_broker_accumulation: float | None = None
    market_regime: dict[str, Any] = field(default_factory=dict)
    market_regime_at_signal: str | None = None
    regime_confidence_at_signal: float | None = None
    regime_stability_at_signal: str | None = None
    days_in_regime_at_signal: int | None = None
    regime_transition_warning_at_signal: str | None = None
    regime_detection_method_at_signal: str | None = None
    # Legacy (schema 1/2) diagnostic-only candidate-level fields — coverage was
    # computed from flow presence divided by two, conviction from
    # raw_group_score / 100. Never fabricated from signal_authority_coverage.
    coverage: float | None = None
    conviction: float | None = None
    # HIGH-2 canonical (schema 3) production-authority coverage.
    signal_authority_coverage: float | None = None
    # HIGH-2 canonical (schema 3) typed setup readiness.
    setup_readiness_status: str | None = None
    setup_readiness_current_phase: str | None = None
    setup_readiness_missing_required_inputs: tuple[str, ...] = ()
    setup_readiness_failed_requirements: tuple[str, ...] = ()
    # Phase E: institutional accumulation evidence fingerprint
    institutional_accumulation_status: str | None = None
    ia_foreign_participation: float | None = None
    ia_foreign_cr4: float | None = None
    ia_foreign_cr8: float | None = None
    ia_cnfb_divergence_20d: float | None = None
    ia_cnfb_divergence_30d: float | None = None
    ia_cnfb_distribution_3d: float | None = None
    ia_foreign_vwap_distance: float | None = None
    ia_foreign_track_coverage: float | None = None
    ia_foreign_track_conviction: float | None = None
    ia_domestic_broker_consistency: float | None = None
    ia_domestic_broker_reversal: float | None = None
    ia_domestic_accumulation_session_ratio: float | None = None
    ia_domestic_buy_vwap_distance: float | None = None
    ia_domestic_broker_hhi_divergence: float | None = None
    ia_bandar_broad_score_normalized: float | None = None
    ia_domestic_track_coverage: float | None = None
    ia_domestic_track_conviction: float | None = None
    ia_counterparty_transfer_asymmetry: float | None = None
    ia_counterparty_buy_hhi: float | None = None
    ia_counterparty_sell_hhi: float | None = None
    ia_coverage_score: float | None = None
    ia_conviction_score: float | None = None
    # Phase F: ticker profile snapshot
    ticker_profile_label: str | None = None    # now stores primary_profile
    ticker_profile_confidence: float | None = None
    tp_market_tier: str | None = None
    tp_foreign_institutional_exposure: float | None = None
    tp_domestic_bandar_exposure: float | None = None
    tp_retail_speculative_exposure: float | None = None
    tp_liquidity_score: float | None = None
    tp_broker_concentration_score: float | None = None
    tp_foreign_flow_score: float | None = None
    tp_volatility_score: float | None = None
    tp_index_membership_score: float | None = None
    tp_market_cap_bucket: str | None = None
    tp_sector: str | None = None
    tp_index_memberships: str | None = None    # comma-joined, e.g. "lq45,idx80"
    tp_coverage_score: float | None = None
    tp_epoch: str | None = None
    # Phase H: Sector context evidence fingerprint
    sc_sector: str | None = None
    sc_peer_count: int | None = None
    sc_sector_20d_return: float | None = None
    sc_sector_vs_ihsg_20d: float | None = None
    sc_sector_breadth: float | None = None
    sc_ticker_vs_sector_rs: float | None = None
    sc_sector_regime: str | None = None
    sc_coverage_score: float | None = None
    # Phase G producer: company quality context evidence fingerprint (DIAGNOSTIC)
    cq_valuation_score: float | None = None
    cq_earnings_trend_score: float | None = None
    cq_analyst_score: float | None = None
    cq_insider_score: float | None = None
    cq_seasonality_score: float | None = None
    cq_aggregate_score: float | None = None
    cq_coverage_score: float | None = None
    cq_present_axis_count: int | None = None
    # Phase G: Alpha/Trigger projection fingerprint
    alpha_score: float | None = None
    trigger_score: float | None = None
    alpha_trigger_final_exact_score: float | None = None
    alpha_trigger_horizon: str | None = None
    alpha_trigger_alpha_weight: float | None = None
    flow_trigger_allowed: bool | None = None
    alpha_trigger_route_metadata: tuple[dict[str, Any], ...] = ()
    alpha_trigger_unavailable_reasons: tuple[str, ...] = ()
    # Volatility context fingerprint (shared with analyze swing diagnostics)
    atr_at_signal: float | None = None
    atr_pct_at_signal: float | None = None
    volatility_bucket_at_signal: str | None = None
    volatility_size_multiplier_at_signal: float | None = None
    # Benchmark excess returns
    benchmark_excess_return_5_session: BenchmarkExcessReturn | None = None
    benchmark_excess_return_20_session: BenchmarkExcessReturn | None = None
    benchmark_excess_return_authority_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize fingerprint to a flat dictionary."""
        return signal_observation_fingerprint_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalObservationFingerprint":
        """Reconstruct fingerprint from dictionary."""
        return signal_observation_fingerprint_from_dict(cls, data)
