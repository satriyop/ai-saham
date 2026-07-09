"""Signal forward labels for replayable ticker-level outcome attribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class SignalLabelHorizon(Enum):
    """Supported Phase B label horizons."""

    TACTICAL_3D = "TACTICAL_3D"
    SWING_10D = "SWING_10D"
    ACCUM_20D = "ACCUM_20D"

    @property
    def trading_days(self) -> int:
        return {
            SignalLabelHorizon.TACTICAL_3D: 3,
            SignalLabelHorizon.SWING_10D: 10,
            SignalLabelHorizon.ACCUM_20D: 20,
        }[self]


class SignalForwardOutcome(Enum):
    """Discrete deterministic outcome label."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    NEUTRAL = "NEUTRAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class SignalObservationFingerprint:
    """Raw signal-time facts persisted for later attribution."""

    setup_family: str | None = None
    setup_name: str | None = None
    setup_phase: str | None = None
    setup_phase_previous: str | None = None
    phase_sequence_valid: bool | None = None
    phase_age_sessions: int | None = None
    phase_strength: float | None = None
    phase_reasons: tuple[str, ...] = ()
    phase_history: tuple[dict[str, Any], ...] = ()
    phase_coverage_score: float | None = None
    phase_conviction_score: float | None = None
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
    rs_vs_ihsg: float | None = None
    volume_ratio: float | None = None
    cnfb: float | None = None
    foreign_participation: float | None = None
    foreign_concentration: float | None = None
    domestic_broker_accumulation: float | None = None
    market_regime: dict[str, Any] = field(default_factory=dict)
    coverage: float | None = None
    conviction: float | None = None
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_family": self.setup_family,
            "setup_name": self.setup_name,
            "setup_phase": self.setup_phase,
            "setup_phase_previous": self.setup_phase_previous,
            "phase_sequence_valid": self.phase_sequence_valid,
            "phase_age_sessions": self.phase_age_sessions,
            "phase_strength": self.phase_strength,
            "phase_reasons": list(self.phase_reasons),
            "phase_history": [dict(entry) for entry in self.phase_history],
            "phase_coverage_score": self.phase_coverage_score,
            "phase_conviction_score": self.phase_conviction_score,
            "strategy_name": self.strategy_name,
            "strategy_rule_name": self.strategy_rule_name,
            "strategy_rule_outcome": self.strategy_rule_outcome,
            "strategy_evidence_route": self.strategy_evidence_route,
            "strategy_evidence_outcome": self.strategy_evidence_outcome,
            "strategy_coverage_score": self.strategy_coverage_score,
            "strategy_conviction_score": self.strategy_conviction_score,
            "strategy_freshness_score": self.strategy_freshness_score,
            "strategy_rationale": list(self.strategy_rationale),
            "rsi": self.rsi,
            "bb_width_pctile": self.bb_width_pctile,
            "vwap_position": self.vwap_position,
            "rs_vs_ihsg": self.rs_vs_ihsg,
            "volume_ratio": self.volume_ratio,
            "cnfb": self.cnfb,
            "foreign_participation": self.foreign_participation,
            "foreign_concentration": self.foreign_concentration,
            "domestic_broker_accumulation": self.domestic_broker_accumulation,
            "market_regime": dict(self.market_regime),
            "coverage": self.coverage,
            "conviction": self.conviction,
            "institutional_accumulation_status": self.institutional_accumulation_status,
            "ia_foreign_participation": self.ia_foreign_participation,
            "ia_foreign_cr4": self.ia_foreign_cr4,
            "ia_foreign_cr8": self.ia_foreign_cr8,
            "ia_cnfb_divergence_20d": self.ia_cnfb_divergence_20d,
            "ia_cnfb_divergence_30d": self.ia_cnfb_divergence_30d,
            "ia_cnfb_distribution_3d": self.ia_cnfb_distribution_3d,
            "ia_foreign_vwap_distance": self.ia_foreign_vwap_distance,
            "ia_foreign_track_coverage": self.ia_foreign_track_coverage,
            "ia_foreign_track_conviction": self.ia_foreign_track_conviction,
            "ia_domestic_broker_consistency": self.ia_domestic_broker_consistency,
            "ia_domestic_broker_reversal": self.ia_domestic_broker_reversal,
            "ia_domestic_accumulation_session_ratio": self.ia_domestic_accumulation_session_ratio,
            "ia_domestic_buy_vwap_distance": self.ia_domestic_buy_vwap_distance,
            "ia_domestic_broker_hhi_divergence": self.ia_domestic_broker_hhi_divergence,
            "ia_bandar_broad_score_normalized": self.ia_bandar_broad_score_normalized,
            "ia_domestic_track_coverage": self.ia_domestic_track_coverage,
            "ia_domestic_track_conviction": self.ia_domestic_track_conviction,
            "ia_counterparty_transfer_asymmetry": self.ia_counterparty_transfer_asymmetry,
            "ia_counterparty_buy_hhi": self.ia_counterparty_buy_hhi,
            "ia_counterparty_sell_hhi": self.ia_counterparty_sell_hhi,
            "ia_coverage_score": self.ia_coverage_score,
            "ia_conviction_score": self.ia_conviction_score,
            "ticker_profile_label": self.ticker_profile_label,
            "ticker_profile_confidence": self.ticker_profile_confidence,
            "tp_market_tier": self.tp_market_tier,
            "tp_foreign_institutional_exposure": self.tp_foreign_institutional_exposure,
            "tp_domestic_bandar_exposure": self.tp_domestic_bandar_exposure,
            "tp_retail_speculative_exposure": self.tp_retail_speculative_exposure,
            "tp_liquidity_score": self.tp_liquidity_score,
            "tp_broker_concentration_score": self.tp_broker_concentration_score,
            "tp_foreign_flow_score": self.tp_foreign_flow_score,
            "tp_volatility_score": self.tp_volatility_score,
            "tp_index_membership_score": self.tp_index_membership_score,
            "tp_market_cap_bucket": self.tp_market_cap_bucket,
            "tp_sector": self.tp_sector,
            "tp_index_memberships": self.tp_index_memberships,
            "tp_coverage_score": self.tp_coverage_score,
            "tp_epoch": self.tp_epoch,
            "sc_sector": self.sc_sector,
            "sc_peer_count": self.sc_peer_count,
            "sc_sector_20d_return": self.sc_sector_20d_return,
            "sc_sector_vs_ihsg_20d": self.sc_sector_vs_ihsg_20d,
            "sc_sector_breadth": self.sc_sector_breadth,
            "sc_ticker_vs_sector_rs": self.sc_ticker_vs_sector_rs,
            "sc_sector_regime": self.sc_sector_regime,
            "sc_coverage_score": self.sc_coverage_score,
            "cq_valuation_score": self.cq_valuation_score,
            "cq_earnings_trend_score": self.cq_earnings_trend_score,
            "cq_analyst_score": self.cq_analyst_score,
            "cq_insider_score": self.cq_insider_score,
            "cq_seasonality_score": self.cq_seasonality_score,
            "cq_aggregate_score": self.cq_aggregate_score,
            "cq_coverage_score": self.cq_coverage_score,
            "cq_present_axis_count": self.cq_present_axis_count,
            "alpha_score": self.alpha_score,
            "trigger_score": self.trigger_score,
            "alpha_trigger_final_exact_score": self.alpha_trigger_final_exact_score,
            "alpha_trigger_horizon": self.alpha_trigger_horizon,
            "alpha_trigger_alpha_weight": self.alpha_trigger_alpha_weight,
            "flow_trigger_allowed": self.flow_trigger_allowed,
            "alpha_trigger_route_metadata": [
                dict(v) for v in self.alpha_trigger_route_metadata
            ],
            "alpha_trigger_unavailable_reasons": list(
                self.alpha_trigger_unavailable_reasons
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalObservationFingerprint":
        regime = data.get("market_regime")
        if regime is None and data.get("market_regime_at_signal") is not None:
            regime = {
                "regime": data.get("market_regime_at_signal"),
                "regime_confidence": data.get("regime_confidence_at_signal"),
                "regime_stability": data.get("regime_stability_at_signal"),
            }
            if data.get("decision_constraints") is not None:
                regime["decision_constraints"] = data.get("decision_constraints")
        return cls(
            setup_family=data.get("setup_family"),
            setup_name=data.get("setup_name"),
            setup_phase=data.get("setup_phase") or data.get("setup_phase_current"),
            setup_phase_previous=data.get("setup_phase_previous"),
            phase_sequence_valid=_optional_bool(data.get("phase_sequence_valid")),
            phase_age_sessions=_optional_int(data.get("phase_age_sessions")),
            phase_strength=_optional_float(data.get("phase_strength")),
            phase_reasons=tuple(str(v) for v in data.get("phase_reasons") or ()),
            phase_history=tuple(
                dict(v) for v in data.get("phase_history") or () if isinstance(v, dict)
            ),
            phase_coverage_score=_optional_float(data.get("phase_coverage_score")),
            phase_conviction_score=_optional_float(data.get("phase_conviction_score")),
            strategy_name=data.get("strategy_name"),
            strategy_rule_name=data.get("strategy_rule_name"),
            strategy_rule_outcome=data.get("strategy_rule_outcome"),
            strategy_evidence_route=data.get("strategy_evidence_route"),
            strategy_evidence_outcome=data.get("strategy_evidence_outcome"),
            strategy_coverage_score=_optional_float(data.get("strategy_coverage_score")),
            strategy_conviction_score=_optional_float(
                data.get("strategy_conviction_score")
            ),
            strategy_freshness_score=_optional_float(
                data.get("strategy_freshness_score")
            ),
            strategy_rationale=tuple(
                str(v) for v in data.get("strategy_rationale") or ()
            ),
            rsi=_optional_float(data.get("rsi", data.get("rsi_at_signal"))),
            bb_width_pctile=_optional_float(
                data.get("bb_width_pctile", data.get("bb_width_pctile_at_signal"))
            ),
            vwap_position=_optional_float(
                data.get("vwap_position", data.get("vwap_position_at_signal"))
            ),
            rs_vs_ihsg=_optional_float(
                data.get("rs_vs_ihsg", data.get("rs_vs_ihsg_20d_at_signal"))
            ),
            volume_ratio=_optional_float(
                data.get("volume_ratio", data.get("volume_ratio_at_signal"))
            ),
            cnfb=_optional_float(data.get("cnfb", data.get("cnfb_20d_at_signal"))),
            foreign_participation=_optional_float(
                data.get(
                    "foreign_participation",
                    data.get("foreign_participation_at_signal"),
                )
            ),
            foreign_concentration=_optional_float(
                data.get(
                    "foreign_concentration",
                    data.get("foreign_concentration_at_signal"),
                )
            ),
            domestic_broker_accumulation=_optional_float(
                data.get(
                    "domestic_broker_accumulation",
                    data.get("domestic_broker_accumulation_at_signal"),
                )
            ),
            market_regime=dict(regime or {}),
            coverage=_optional_float(data.get("coverage", data.get("coverage_score"))),
            conviction=_optional_float(data.get("conviction", data.get("conviction_score"))),
            institutional_accumulation_status=data.get("institutional_accumulation_status"),
            ia_foreign_participation=_optional_float(data.get("ia_foreign_participation")),
            ia_foreign_cr4=_optional_float(data.get("ia_foreign_cr4")),
            ia_foreign_cr8=_optional_float(data.get("ia_foreign_cr8")),
            ia_cnfb_divergence_20d=_optional_float(data.get("ia_cnfb_divergence_20d")),
            ia_cnfb_divergence_30d=_optional_float(data.get("ia_cnfb_divergence_30d")),
            ia_cnfb_distribution_3d=_optional_float(data.get("ia_cnfb_distribution_3d")),
            ia_foreign_vwap_distance=_optional_float(data.get("ia_foreign_vwap_distance")),
            ia_foreign_track_coverage=_optional_float(data.get("ia_foreign_track_coverage")),
            ia_foreign_track_conviction=_optional_float(data.get("ia_foreign_track_conviction")),
            ia_domestic_broker_consistency=_optional_float(data.get("ia_domestic_broker_consistency")),
            ia_domestic_broker_reversal=_optional_float(data.get("ia_domestic_broker_reversal")),
            ia_domestic_accumulation_session_ratio=_optional_float(data.get("ia_domestic_accumulation_session_ratio")),
            ia_domestic_buy_vwap_distance=_optional_float(data.get("ia_domestic_buy_vwap_distance")),
            ia_domestic_broker_hhi_divergence=_optional_float(data.get("ia_domestic_broker_hhi_divergence")),
            ia_bandar_broad_score_normalized=_optional_float(data.get("ia_bandar_broad_score_normalized")),
            ia_domestic_track_coverage=_optional_float(data.get("ia_domestic_track_coverage")),
            ia_domestic_track_conviction=_optional_float(data.get("ia_domestic_track_conviction")),
            ia_counterparty_transfer_asymmetry=_optional_float(data.get("ia_counterparty_transfer_asymmetry")),
            ia_counterparty_buy_hhi=_optional_float(data.get("ia_counterparty_buy_hhi")),
            ia_counterparty_sell_hhi=_optional_float(data.get("ia_counterparty_sell_hhi")),
            ia_coverage_score=_optional_float(data.get("ia_coverage_score")),
            ia_conviction_score=_optional_float(data.get("ia_conviction_score")),
            ticker_profile_label=data.get("ticker_profile_label"),
            ticker_profile_confidence=_optional_float(
                data.get("ticker_profile_confidence")
            ),
            tp_market_tier=data.get("tp_market_tier"),
            tp_foreign_institutional_exposure=_optional_float(
                data.get("tp_foreign_institutional_exposure")
            ),
            tp_domestic_bandar_exposure=_optional_float(
                data.get("tp_domestic_bandar_exposure")
            ),
            tp_retail_speculative_exposure=_optional_float(
                data.get("tp_retail_speculative_exposure")
            ),
            tp_liquidity_score=_optional_float(data.get("tp_liquidity_score")),
            tp_broker_concentration_score=_optional_float(
                data.get("tp_broker_concentration_score")
            ),
            tp_foreign_flow_score=_optional_float(data.get("tp_foreign_flow_score")),
            tp_volatility_score=_optional_float(data.get("tp_volatility_score")),
            tp_index_membership_score=_optional_float(
                data.get("tp_index_membership_score")
            ),
            tp_market_cap_bucket=data.get("tp_market_cap_bucket"),
            tp_sector=data.get("tp_sector"),
            tp_index_memberships=data.get("tp_index_memberships"),
            tp_coverage_score=_optional_float(data.get("tp_coverage_score")),
            tp_epoch=data.get("tp_epoch"),
            sc_sector=data.get("sc_sector"),
            sc_peer_count=_optional_int(data.get("sc_peer_count")),
            sc_sector_20d_return=_optional_float(data.get("sc_sector_20d_return")),
            sc_sector_vs_ihsg_20d=_optional_float(data.get("sc_sector_vs_ihsg_20d")),
            sc_sector_breadth=_optional_float(data.get("sc_sector_breadth")),
            sc_ticker_vs_sector_rs=_optional_float(data.get("sc_ticker_vs_sector_rs")),
            sc_sector_regime=data.get("sc_sector_regime"),
            sc_coverage_score=_optional_float(data.get("sc_coverage_score")),
            cq_valuation_score=_optional_float(data.get("cq_valuation_score")),
            cq_earnings_trend_score=_optional_float(data.get("cq_earnings_trend_score")),
            cq_analyst_score=_optional_float(data.get("cq_analyst_score")),
            cq_insider_score=_optional_float(data.get("cq_insider_score")),
            cq_seasonality_score=_optional_float(data.get("cq_seasonality_score")),
            cq_aggregate_score=_optional_float(data.get("cq_aggregate_score")),
            cq_coverage_score=_optional_float(data.get("cq_coverage_score")),
            cq_present_axis_count=_optional_int(data.get("cq_present_axis_count")),
            alpha_score=_optional_float(data.get("alpha_score")),
            trigger_score=_optional_float(data.get("trigger_score")),
            alpha_trigger_final_exact_score=_optional_float(
                data.get("alpha_trigger_final_exact_score")
            ),
            alpha_trigger_horizon=data.get("alpha_trigger_horizon"),
            alpha_trigger_alpha_weight=_optional_float(
                data.get("alpha_trigger_alpha_weight")
            ),
            flow_trigger_allowed=_optional_bool(data.get("flow_trigger_allowed")),
            alpha_trigger_route_metadata=tuple(
                dict(v)
                for v in data.get("alpha_trigger_route_metadata") or ()
                if isinstance(v, dict)
            ),
            alpha_trigger_unavailable_reasons=tuple(
                str(v) for v in data.get("alpha_trigger_unavailable_reasons") or ()
            ),
        )


@dataclass(frozen=True)
class SignalForwardLabel:
    """Deterministic forward outcome label for one saved signal observation."""

    ticker: str
    signal_date: date
    horizon: SignalLabelHorizon
    entry_reference_price: Decimal | None
    label_window_start: date | None
    label_window_end: date | None
    close_return: float | None
    max_forward_return: float | None
    max_adverse_excursion: float | None
    days_to_peak: int | None
    days_to_trough: int | None
    stop_would_trigger: bool | None
    target_would_trigger: bool | None
    outcome_label: SignalForwardOutcome
    unavailable_reason: str | None
    fingerprint: SignalObservationFingerprint
    observation_captured_at: datetime | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if self.entry_reference_price is not None and self.entry_reference_price <= Decimal("0"):
            raise ValueError("entry_reference_price must be positive when provided")
        if self.schema_version != 1:
            raise ValueError(
                f"unsupported signal forward label schema_version={self.schema_version}"
            )
        if self.outcome_label == SignalForwardOutcome.UNAVAILABLE and not self.unavailable_reason:
            raise ValueError("UNAVAILABLE labels require unavailable_reason")
        if self.outcome_label != SignalForwardOutcome.UNAVAILABLE and self.unavailable_reason:
            raise ValueError("available labels must not set unavailable_reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticker": self.ticker,
            "signal_date": self.signal_date.isoformat(),
            "horizon": self.horizon.value,
            "entry_reference_price": (
                str(self.entry_reference_price) if self.entry_reference_price is not None else None
            ),
            "label_window_start": (
                self.label_window_start.isoformat() if self.label_window_start else None
            ),
            "label_window_end": (
                self.label_window_end.isoformat() if self.label_window_end else None
            ),
            "close_return": self.close_return,
            "max_forward_return": self.max_forward_return,
            "max_adverse_excursion": self.max_adverse_excursion,
            "days_to_peak": self.days_to_peak,
            "days_to_trough": self.days_to_trough,
            "stop_would_trigger": self.stop_would_trigger,
            "target_would_trigger": self.target_would_trigger,
            "outcome_label": self.outcome_label.value,
            "unavailable_reason": self.unavailable_reason,
            "fingerprint": self.fingerprint.to_dict(),
            "observation_captured_at": (
                self.observation_captured_at.isoformat() if self.observation_captured_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalForwardLabel":
        return cls(
            ticker=str(data["ticker"]).upper(),
            signal_date=_parse_date(data["signal_date"]),
            horizon=SignalLabelHorizon(data["horizon"]),
            entry_reference_price=(
                Decimal(str(data["entry_reference_price"]))
                if data.get("entry_reference_price") is not None
                else None
            ),
            label_window_start=_parse_optional_date(data.get("label_window_start")),
            label_window_end=_parse_optional_date(data.get("label_window_end")),
            close_return=_optional_float(data.get("close_return")),
            max_forward_return=_optional_float(data.get("max_forward_return")),
            max_adverse_excursion=_optional_float(data.get("max_adverse_excursion")),
            days_to_peak=_optional_int(data.get("days_to_peak")),
            days_to_trough=_optional_int(data.get("days_to_trough")),
            stop_would_trigger=_optional_bool(data.get("stop_would_trigger")),
            target_would_trigger=_optional_bool(data.get("target_would_trigger")),
            outcome_label=SignalForwardOutcome(data["outcome_label"]),
            unavailable_reason=data.get("unavailable_reason"),
            fingerprint=SignalObservationFingerprint.from_dict(data.get("fingerprint") or {}),
            observation_captured_at=_parse_optional_datetime(data.get("observation_captured_at")),
            schema_version=int(data.get("schema_version", 1)),
        )


def _parse_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _parse_optional_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    return _parse_date(value)


def _parse_optional_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
