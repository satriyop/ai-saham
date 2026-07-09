"""
AccumulationScreenUseCase — multi-stock foreign accumulation screener.

Scans a list of tickers for sustained foreign investor accumulation patterns.
Foreign-flow scoring is delegated to ScoreForeignFlowUseCase;
this use case owns orchestration, filtering, enrichment, and sorting.

Intraday vs Swing usage:
  This screener produces a SWING WATCHLIST (5–20 day horizon).
  For intraday timing, cross-reference with `saham screen pre-open`.

Layer: Application
Depends on: Domain ports only — no infrastructure imports
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from src.domain.ports.candidate_observations_repository import CandidateObservation

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.value_objects.analyst_consensus import AnalystConsensus
    from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
    from src.domain.value_objects.company_fundamentals import CompanyFundamentals
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.forward_estimates import ForwardEstimates
    from src.domain.value_objects.institutional_accumulation_evidence import InstitutionalAccumulationEvidence
    from src.domain.value_objects.risk_assessment import RiskAssessment
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot
    from src.domain.value_objects.seasonal_edge import SeasonalEdge
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.shareholding_composition import ShareholdingComposition
    from src.domain.value_objects.ticker_notation import TickerNotationSnapshot
    from src.domain.value_objects.trade_setup import TradeSetup

from src.application.ports.corporate_action_repository import CorporateActionRepository
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.stats import foreign_vwap_discount_pct
from src.application.use_case.score_foreign_flow_use_case import (
    ScoreForeignFlowRequest,
    ScoreForeignFlowUseCase,
)
from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.forward_estimates_provider import ForwardEstimatesProvider
from src.domain.ports.fundamentals_provider import FundamentalsProvider
from src.domain.ports.insider_activity_provider import InsiderActivityProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.seasonality_provider import SeasonalityProvider
from src.domain.ports.shareholding_provider import ShareholdingProvider
from src.domain.ports.ticker_notation_provider import TickerNotationProvider
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence
from src.domain.value_objects.foreign_flow_score_breakdown import ForeignFlowScoreBreakdown
from src.domain.value_objects.idx_market import SHARES_PER_LOT

# Default setup targets (1:1 R:R, regime-unaware fallback)
_DEFAULT_TAKE_PROFIT = Decimal("5")
_DEFAULT_STOP_LOSS = Decimal("5")

# Regime-specific targets (validated direction: IHSG has documented regime cycles)
# MCE vocabulary (RISK_ON/NEUTRAL/VOLATILE/RISK_OFF).
_REGIME_TARGETS: dict[str, tuple[Decimal, Decimal]] = {
    "RISK_ON": (Decimal("8"), Decimal("4")),  # 2:1 R:R — trending market
    "NEUTRAL": (Decimal("5"), Decimal("5")),  # 1:1 R:R — range-bound
    "VOLATILE": (Decimal("3"), Decimal("3")),  # tight — minimize exposure
    "RISK_OFF": (Decimal("3"), Decimal("3")),  # capital preservation
}


def resolve_setup_targets(
    regime: str | None,
    config: Any | None = None,
) -> tuple[Decimal, Decimal]:
    """Return (take_profit_pct, stop_loss_pct) for the foreign-bounce setup.

    Precedence: YAML config overrides > regime defaults > hardcoded fallback.
    All values are in percentage points (e.g. Decimal("5") = 5%).
    """
    if config:
        targets = getattr(config, "setup_targets", None)
        if targets is None and isinstance(config, dict):
            targets = config.get("setup_targets", config)
        targets = targets or {}
        regime_key = (regime or "default").lower()
        tier = targets.get(regime_key) or targets.get("default", {})
        if tier:
            if isinstance(tier, dict):
                tp = tier.get("take_profit_pct")
                sl = tier.get("stop_loss_pct")
            else:
                tp = getattr(tier, "take_profit_pct", None)
                sl = getattr(tier, "stop_loss_pct", None)
            if tp is not None and sl is not None:
                return Decimal(str(tp)), Decimal(str(sl))

    if regime and regime.upper() in _REGIME_TARGETS:
        return _REGIME_TARGETS[regime.upper()]

    return _DEFAULT_TAKE_PROFIT, _DEFAULT_STOP_LOSS


def _is_usable_broker_summary(summary) -> bool:
    """Return True when a broker summary is safe for accumulation metrics."""
    return (
        summary.total_value > Decimal("0")
        and summary.total_lot >= 0
        and summary.foreign_buy_lot >= 0
        and summary.foreign_sell_lot >= 0
    )


# Tier 1 — pure foreign institutional desks (custodian + prime brokerage).
# These are the codes whose net_lot signal most reliably tracks foreign institutional intent.
# YP (Indo Premier / Mirae) is domestic and excluded here even though it's in
# _INSTITUTIONAL_PROXY_CODES for flow aggregation — it doesn't signal foreign custody.
TIER1_FOREIGN_BROKERS = frozenset({"AK", "BK", "ZP", "KZ", "YU", "RX", "HD", "CP", "DR"})

# Broker Concentration Index (BCI) tiers
BCI_CLUSTER = "CLUSTER"  # 3+ Tier 1 codes in window top net-buyers → +15 pts
BCI_STABLE = "STABLE"  # 1–2 Tier 1 codes                         → +5 pts
BCI_RETAIL = "RETAIL-LED"  # 0 Tier 1 codes                           → +0 pts


@dataclass
class AccumulationScreenRequest:
    """Input parameters for the screener."""

    tickers: list[str]
    window_days: int = 7  # latest broker sessions: 7, 30, or 90
    min_net_buy_days: int = 2  # skip tickers with fewer qualifying days
    min_foreign_flow_score: float = 0.0  # filter: only include composite foreign-flow score >= this
    min_foreign_flow_score_enabled: bool = True
    min_signal_score: float = 0.0  # optional SignalEngine score filter
    min_signal_score_enabled: bool = False
    rsi_period: int | None = None
    sma_period: int | None = None
    as_of_date: date | None = None  # deterministic replay date; defaults to today
    # Phase 2.2 — resistance-proximity gate
    resistance_gate_enabled: bool = True
    resistance_headroom_min_pct: float = 5.0  # % headroom required to keep ENTER verdict
    # Phase 2.3 — regime-adaptive TP/SL
    regime: str | None = None  # BULLISH / SIDEWAYS / WEAK / RISK_OFF
    # Phase 3.1 — corporate action risk window
    ex_date_warning_days: int = 10  # flag risk if ex/cum/event date within this many days
    # Phase 3.2 — sector breadth confirmation
    sector_breadth_enabled: bool = True
    sector_breadth_threshold: float = 0.60  # min fraction of peers with net_buy_ratio > 0
    sector_breadth_bonus_pts: float = 10.0  # bonus pts when threshold is met
    sector_breadth_min_tickers: int = 3  # min peers in result set to compute breadth
    # BCI — Tier 1 broker codes for Broker Concentration Index scoring.
    # Default mirrors TIER1_FOREIGN_BROKERS; override via config to tune without code change.
    tier1_broker_codes: frozenset[str] = field(default_factory=lambda: TIER1_FOREIGN_BROKERS)
    bci_cluster_min_count: int = 3
    bci_stable_min_count: int = 1
    # Market cap floor — tickers below this IDR value are excluded (0 = disabled)
    min_market_cap_idr: int = 0
    # Piotroski F-Score floor (0–9). Tickers below this are excluded (0 = disabled)
    min_piotroski: int = 0
    strategy_name: str | None = None

    def __init__(
        self,
        tickers: list[str],
        window_days: int = 7,
        min_net_buy_days: int = 2,
        min_foreign_flow_score: float = 0.0,
        min_foreign_flow_score_enabled: bool = True,
        min_signal_score: float = 0.0,
        min_signal_score_enabled: bool = False,
        rsi_period: int | None = None,
        sma_period: int | None = None,
        as_of_date: date | None = None,
        resistance_gate_enabled: bool = True,
        resistance_headroom_min_pct: float = 5.0,
        regime: str | None = None,
        ex_date_warning_days: int = 10,
        sector_breadth_enabled: bool = True,
        sector_breadth_threshold: float = 0.60,
        sector_breadth_bonus_pts: float = 10.0,
        sector_breadth_min_tickers: int = 3,
        tier1_broker_codes: frozenset[str] | None = None,
        bci_cluster_min_count: int = 3,
        bci_stable_min_count: int = 1,
        min_market_cap_idr: int = 0,
        min_piotroski: int = 0,
        strategy_name: str | None = None,
    ) -> None:
        self.tickers = tickers
        self.window_days = window_days
        self.min_net_buy_days = min_net_buy_days
        self.min_foreign_flow_score = min_foreign_flow_score
        self.min_foreign_flow_score_enabled = min_foreign_flow_score_enabled
        self.min_signal_score = min_signal_score
        self.min_signal_score_enabled = min_signal_score_enabled
        self.rsi_period = rsi_period
        self.sma_period = sma_period
        self.as_of_date = as_of_date
        self.resistance_gate_enabled = resistance_gate_enabled
        self.resistance_headroom_min_pct = resistance_headroom_min_pct
        self.regime = regime
        self.ex_date_warning_days = ex_date_warning_days
        self.sector_breadth_enabled = sector_breadth_enabled
        self.sector_breadth_threshold = sector_breadth_threshold
        self.sector_breadth_bonus_pts = sector_breadth_bonus_pts
        self.sector_breadth_min_tickers = sector_breadth_min_tickers
        self.tier1_broker_codes = tier1_broker_codes or TIER1_FOREIGN_BROKERS
        self.bci_cluster_min_count = bci_cluster_min_count
        self.bci_stable_min_count = bci_stable_min_count
        self.min_market_cap_idr = min_market_cap_idr
        self.min_piotroski = min_piotroski
        self.strategy_name = strategy_name


@dataclass(frozen=True)
class AccumulationDerivedFeaturePolicy:
    """Tunable windows for derived features used by the accumulation screen."""

    rsi_period: int = 14
    trend_sma_period: int = 20
    trend_threshold_pct: float = 2.0
    bb_period: int = 20
    bb_history: int = 60
    market_vwap_period: int = 20
    resistance_ma_period: int = 200
    resistance_high_period: int = 252
    insider_lookback_days: int = 90


@dataclass
class AccumulationCandidate:
    """Screener result for a single ticker."""

    ticker: str
    window_days: int
    net_buy_days: int  # days with positive net foreign value
    total_days: int  # total days with broker data in window
    net_buy_ratio: float  # net_buy_days / total_days (0–1)
    total_net_value: Decimal  # cumulative net foreign IDR
    consecutive_streak: int  # current run of consecutive buy days
    foreign_vwap: Decimal | None  # volume-weighted avg foreign buy price
    current_price: Decimal  # latest close price
    vwap_discount_pct: float | None  # (vwap - price) / price * 100
    # positive = foreigners are underwater
    rsi: float | None
    trend: str  # "UP" | "DOWN" | "SIDE"
    foreign_flow_score: float  # 0-100 composite foreign-flow score
    top_brokers: list[str] | None  # per-broker codes (Stockbit only)
    institutional_flag: bool  # True if major institutional broker present
    # Improvement #1: flow ratio signal
    avg_flow_ratio: float | None = None  # avg % of daily turnover that's foreign
    foreign_flow_score_breakdown: ForeignFlowScoreBreakdown | None = None
    foreign_flow_evidence: ForeignFlowEvidence | None = None
    # Improvement #3: BB squeeze
    bb_width: float | None = None  # current BB Width %
    bb_width_pctile: float | None = None  # 0..1 vs last 60 days (lower = tighter)
    # BCI — Broker Concentration Index
    bci_label: str | None = None  # "CLUSTER" | "STABLE" | "RETAIL-LED" | None
    bci_tier1_count: int = 0  # distinct Tier 1 foreign desks in net-buyers
    vwap_pct: float | None = None  # (price - VWAP20) / VWAP20 * 100; negative = below VWAP
    # Phase 2.2 — resistance-proximity gate
    ma200: Decimal | None = None  # 200-day SMA of close prices
    week52_high: Decimal | None = None  # 52-week (252-day) highest high
    nearest_resistance_pct: float | None = None  # % distance to nearest resistance above price
    resistance_flag: bool = False  # True when nearest resistance < headroom_min_pct
    # Phase 3.1 — corporate action risk flags (sourced from Stockbit live calendar)
    dividend_risk: bool = False  # True when ex-date falls within hold window
    rights_issue_risk: bool = False  # True when rights issue in hold window (dilution risk)
    upcoming_rups: list[str] = field(default_factory=list)  # RUPS event detail strings
    # Phase 3.3 — seasonality signal (sourced from Stockbit 5-year monthly stats)
    seasonal_edge: "SeasonalEdge | None" = None  # current-month statistical edge
    # Insider activity — IDX-filed director/commissioner buy transactions
    insider_buying: bool = False  # True when insider bought within lookback window
    recent_insider_buys: list[str] = field(default_factory=list)  # human-readable labels
    insider_net_buy_ratio: float | None = None
    # Analyst consensus — aggregated analyst buy/hold/sell + price target
    analyst_consensus: "AnalystConsensus | None" = None
    # Shareholding composition — institutional %, individual %, top controlling holder
    shareholding: "ShareholdingComposition | None" = None
    # Bandar detector — Stockbit's proprietary institutional operator accumulation signal
    bandar_detector: "BandarDetectorSnapshot | None" = None
    # Company fundamentals — P/E, ROE, Net Profit Margin, Piotroski F-Score (quarterly)
    fundamentals: "CompanyFundamentals | None" = None
    # Ticker status / special notation — display-only Stockbit context
    ticker_notation: "TickerNotationSnapshot | None" = None
    # Phase 3.2 — sector breadth confirmation
    sector_breadth_pct: float | None = None  # % of group peers with positive net_buy_ratio
    sector_breadth_bonus: float = 0.0  # bonus pts applied (0 if threshold not met)
    # Data currency — dates of the most recent loaded records; None if no data
    latest_candle_date: date | None = None
    latest_broker_date: date | None = None
    # Forward EPS/Revenue estimates (Stockbit analyst consensus endpoint)
    forward_estimates: "ForwardEstimates | None" = None
    # Composite signal — all enrichment dimensions combined into 0–100 score
    signal_assessment: "AssessSignalResponse | None" = None
    # Phase E: post-screening risk assessment (populated by risk funnel when configured)
    risk_assessment: "RiskAssessment | None" = None
    # Unified trade action verdict — requires both signal_assessment and risk funnel
    trade_setup: "TradeSetup | None" = None
    # Accumulation-lifecycle diagnostic (ACCUMULATION/COMPRESSION/BREAKOUT_CONFIRMATION/
    # EXHAUSTION/DISTRIBUTION/FAILED/NONE); None when detection is unavailable or fails.
    setup_phase: "SetupPhaseSnapshot | None" = None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "window_days": self.window_days,
            "net_buy_days": self.net_buy_days,
            "total_days": self.total_days,
            "net_buy_ratio": round(self.net_buy_ratio, 4),
            "total_net_value": str(self.total_net_value),
            "consecutive_streak": self.consecutive_streak,
            "foreign_vwap": str(self.foreign_vwap) if self.foreign_vwap else None,
            "current_price": str(self.current_price),
            "vwap_discount_pct": round(self.vwap_discount_pct, 2)
            if self.vwap_discount_pct is not None
            else None,
            "rsi": round(self.rsi, 2) if self.rsi is not None else None,
            "trend": self.trend,
            "foreign_flow_score": self.foreign_flow_score,
            "top_brokers": self.top_brokers,
            "institutional_flag": self.institutional_flag,
            "bci_label": self.bci_label,
            "bci_tier1_count": self.bci_tier1_count,
            "vwap_pct": round(self.vwap_pct, 2) if self.vwap_pct is not None else None,
            "avg_flow_ratio": round(self.avg_flow_ratio, 2)
            if self.avg_flow_ratio is not None
            else None,
            "foreign_flow_score_breakdown": (
                self.foreign_flow_score_breakdown.to_dict()
                if self.foreign_flow_score_breakdown is not None
                else None
            ),
            "foreign_flow_evidence": (
                self.foreign_flow_evidence.to_dict()
                if self.foreign_flow_evidence is not None
                else None
            ),
            "bb_width": round(self.bb_width, 2) if self.bb_width is not None else None,
            "bb_width_pctile": round(self.bb_width_pctile, 3)
            if self.bb_width_pctile is not None
            else None,
            "dividend_risk": self.dividend_risk,
            "rights_issue_risk": self.rights_issue_risk,
            "upcoming_rups": self.upcoming_rups,
            "seasonal_score": round(self.seasonal_edge.score, 2) if self.seasonal_edge else None,
            "seasonal_label": self.seasonal_edge.label if self.seasonal_edge else None,
            "insider_buying": self.insider_buying,
            "recent_insider_buys": self.recent_insider_buys,
            "insider_net_buy_ratio": round(self.insider_net_buy_ratio, 4)
            if self.insider_net_buy_ratio is not None
            else None,
            "analyst_consensus": self.analyst_consensus.to_dict()
            if self.analyst_consensus
            else None,
            "shareholding": self.shareholding.to_dict() if self.shareholding else None,
            "bandar_detector": self.bandar_detector.to_dict() if self.bandar_detector else None,
            "fundamentals": self.fundamentals.to_dict() if self.fundamentals else None,
            "ticker_notation": self.ticker_notation.to_dict() if self.ticker_notation else None,
            "latest_candle_date": self.latest_candle_date.isoformat()
            if self.latest_candle_date
            else None,
            "latest_broker_date": self.latest_broker_date.isoformat()
            if self.latest_broker_date
            else None,
            "forward_estimates": self.forward_estimates.to_dict()
            if self.forward_estimates
            else None,
            "signal_assessment": {
                "score": self.signal_assessment.assessment.score,
                "strength": self.signal_assessment.assessment.strength.value,
                "entry_quality": self.signal_assessment.assessment.entry_quality.value,
                "breakdown": self.signal_assessment.assessment.breakdown_dict,
                "coverage_score": self.signal_assessment.assessment.coverage_score,   # canonical
                "confidence_score": self.signal_assessment.assessment.confidence_score,  # legacy alias
                "coverage_warning": self.signal_assessment.coverage_warning,
                "decision_constraints": (
                    self.signal_assessment.assessment.decision_constraints.to_dict()
                    if self.signal_assessment.assessment.decision_constraints
                    else None
                ),
            }
            if self.signal_assessment
            else None,
            "risk_status": self.risk_assessment.risk_level_name if self.risk_assessment else None,
            "risk_confidence": self.risk_assessment.confidence if self.risk_assessment else None,
            "risk_gate": self.risk_assessment.gate_triggered if self.risk_assessment else None,
            "setup_phase": self.setup_phase.to_dict() if self.setup_phase else None,
        }


@dataclass
class AccumulationScreenResponse:
    """Screener output."""

    candidates: list[AccumulationCandidate]  # sorted by foreign-flow score descending
    screened_at: date
    window_days: int
    total_tickers_checked: int
    tickers_skipped: int  # insufficient data
    provider: str  # "idx" or "stockbit"


def _trade_action_rank(candidate: "AccumulationCandidate") -> int:
    if candidate.trade_setup is None:
        return 0
    action = candidate.trade_setup.action.value
    return {
        "ENTER": 5,
        "WATCH": 4,
        "AVOID": 2,
        "BLOCKED_EXECUTION": 1,
        "BLOCKED_STRUCTURAL": 0,
    }.get(action, 0)


def _screen_sort_key(candidate: "AccumulationCandidate") -> tuple[float, float, float, float]:
    """Default screener ordering: verdict, signal, foreign-flow score, seasonality."""
    return (
        float(_trade_action_rank(candidate)),
        float(candidate.signal_assessment.assessment.score if candidate.signal_assessment else 0),
        candidate.foreign_flow_score,
        candidate.seasonal_edge.score if candidate.seasonal_edge else 0.0,
    )


def _candidate_observation_payload(
    candidate: "AccumulationCandidate",
    *,
    screen_result: str,
    flow_ev: "FlowConfirmationEvidence | None",
    setup_phase: "SetupPhaseSnapshot | None",
    snapshot_date: date,
    captured_at: datetime,
    request: "AccumulationScreenRequest",
    strategy_evidence: "StrategyEvidence | None" = None,
    ia_evidence: "InstitutionalAccumulationEvidence | None" = None,
    tp_snapshot: "TickerProfileSnapshot | None" = None,
    sc_evidence: "SectorContextEvidence | None" = None,
    cq_evidence: "CompanyQualityContextEvidence | None" = None,
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
    candidate: "AccumulationCandidate",
    signal: "AssessSignalResponse | None",
    flow_ev: "FlowConfirmationEvidence | None",
    setup_phase: "SetupPhaseSnapshot | None" = None,
    strategy_evidence: "StrategyEvidence | None" = None,
    ia_evidence: "InstitutionalAccumulationEvidence | None" = None,
    tp_snapshot: "TickerProfileSnapshot | None" = None,
    sc_evidence: "SectorContextEvidence | None" = None,
    cq_evidence: "CompanyQualityContextEvidence | None" = None,
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
    return {
        "setup_family": constraints.get("setup_family"),
        "setup_name": constraints.get("setup_name"),
        **phase_dict,
        **strategy_dict,
        **ia_dict,
        **tp_dict,
        **sc_dict,
        **cq_dict,
        **alpha_trigger_dict,
        "rsi_at_signal": candidate.rsi,
        "bb_width_pctile_at_signal": candidate.bb_width_pctile,
        "vwap_position_at_signal": candidate.vwap_pct,
        "rs_vs_ihsg_20d_at_signal": None,
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
        "market_regime_at_signal": constraints.get("regime"),
        "regime_confidence_at_signal": None,
        "regime_stability_at_signal": None,
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


def _simple_return(
    candles: list[Any] | tuple[Any, ...],
    *,
    lookback: int,
    min_valid: int,
) -> float | None:
    sorted_candles = sorted(candles, key=lambda c: c.date)
    window = sorted_candles[-lookback:] if len(sorted_candles) >= lookback else sorted_candles
    valid = [c for c in window if getattr(c, "close", None) and float(c.close) > 0.0]
    if len(valid) < min_valid:
        return None
    reference = float(valid[0].close)
    if reference <= 0.0:
        return None
    return (float(valid[-1].close) - reference) / reference


class AccumulationScreenUseCase:
    """
    Scan multiple tickers for foreign accumulation patterns.

    Reads from local repositories only — no network calls.
    All data must be fetched beforehand via `saham fetch market`.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        corporate_action_repo: "CorporateActionRepository | None" = None,
        seasonality_provider: "SeasonalityProvider | None" = None,
        insider_activity_provider: "InsiderActivityProvider | None" = None,
        analyst_consensus_provider: "AnalystConsensusProvider | None" = None,
        forward_estimates_provider: "ForwardEstimatesProvider | None" = None,
        shareholding_provider: "ShareholdingProvider | None" = None,
        bandar_detector_provider: "BandarDetectorProvider | None" = None,
        fundamentals_provider: "FundamentalsProvider | None" = None,
        ticker_notation_provider: "TickerNotationProvider | None" = None,
        idx_groups: "dict[str, list[str]] | None" = None,
        risk_use_case: "AssessRiskUseCase | None" = None,
        signal_engine: "SignalEngine | None" = None,
        candidate_observations_repository: "CandidateObservationsRepository | None" = None,
        foreign_flow_score_use_case: ScoreForeignFlowUseCase | None = None,
        derived_feature_policy: AccumulationDerivedFeaturePolicy | None = None,
    ) -> None:
        from src.application.services.signal_engine import SignalEngine as _SignalEngine
        from src.application.services.flow_confirmation_evidence_builder import (
            FlowConfirmationEvidenceBuilder,
        )

        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._corp_action_repo = corporate_action_repo
        self._seasonality_provider = seasonality_provider
        self._insider_provider = insider_activity_provider
        self._analyst_provider = analyst_consensus_provider
        self._forward_estimates_provider = forward_estimates_provider
        self._shareholding_provider = shareholding_provider
        self._bandar_provider = bandar_detector_provider
        self._fundamentals_provider = fundamentals_provider
        self._ticker_notation_provider = ticker_notation_provider
        self._risk_use_case = risk_use_case
        self._signal_engine = signal_engine or _SignalEngine()
        self._candidate_observations_repo = candidate_observations_repository
        self._foreign_flow_score_uc = foreign_flow_score_use_case or ScoreForeignFlowUseCase()
        self._derived_features = derived_feature_policy or AccumulationDerivedFeaturePolicy()
        # Derive weights from the same policy ScoreForeignFlowUseCase uses, so
        # the two can never drift apart (see ADR-039).
        self._flow_confirmation_builder = FlowConfirmationEvidenceBuilder(
            foreign_flow_score_policy=self._foreign_flow_score_uc.policy
        )
        # idx_groups: {group_name: [ticker, ...]} from config/idx_groups.yaml
        # Build a reverse map: ticker → group_name for fast lookup
        self._ticker_to_group: dict[str, str] = {}
        if idx_groups:
            for group_name, tickers in idx_groups.items():
                for t in tickers:
                    self._ticker_to_group[t.upper()] = group_name

    def execute(self, request: AccumulationScreenRequest) -> AccumulationScreenResponse:
        today = request.as_of_date or date.today()
        candidates: list[AccumulationCandidate] = []
        # Collects (candidate, screen_result, flow_ev) for ALL evaluated tickers —
        # survivors and filtered-out alike. Rejected records are negative samples
        # for future tuning (Phase 7: "rejected candidates become learnable").
        all_results: list[tuple[AccumulationCandidate, str, FlowConfirmationEvidence | None]] = []
        skipped = 0
        uses_stockbit = False

        for ticker in request.tickers:
            result = self._evaluate_ticker(
                ticker=ticker,
                window_days=request.window_days,
                today=today,
                min_net_buy_days=request.min_net_buy_days,
                rsi_period=request.rsi_period or self._derived_features.rsi_period,
                sma_period=request.sma_period or self._derived_features.trend_sma_period,
                tier1_broker_codes=request.tier1_broker_codes,
                bci_cluster_min_count=request.bci_cluster_min_count,
                bci_stable_min_count=request.bci_stable_min_count,
            )

            if result is None:
                skipped += 1
                continue

            if result.top_brokers is not None:
                uses_stockbit = True

            # Early pruning: fetch fundamentals first when market_cap or piotroski
            # gates are active. Avoids 6+ enrichment queries for tickers that will
            # be skipped by these structural filters.
            fundamentals_fetched = False
            if self._fundamentals_provider is not None and (
                request.min_market_cap_idr > 0 or request.min_piotroski > 0
            ):
                result.fundamentals = self._fundamentals_provider.get_fundamentals(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )
                fundamentals_fetched = True

                # Market cap floor gate
                if request.min_market_cap_idr > 0 and (
                    result.fundamentals is None
                    or result.fundamentals.market_cap_idr is None
                    or result.fundamentals.market_cap_idr < request.min_market_cap_idr
                ):
                    cap_b = (
                        result.fundamentals.market_cap_idr // 1_000_000_000
                        if result.fundamentals and result.fundamentals.market_cap_idr
                        else None
                    )
                    logger.debug(
                        "Skip %s: market_cap %sB IDR < floor %dB IDR",
                        result.ticker,
                        cap_b,
                        request.min_market_cap_idr // 1_000_000_000,
                    )
                    skipped += 1
                    continue

                # Piotroski floor gate
                if request.min_piotroski > 0:
                    fscore = (
                        result.fundamentals.piotroski_f_score
                        if result.fundamentals is not None
                        else None
                    )
                    if fscore is None or fscore < request.min_piotroski:
                        skipped += 1
                        continue

            evidence_resp = self._foreign_flow_score_uc.execute(
                ScoreForeignFlowRequest(
                    ticker=result.ticker,
                    snapshot_date=today,
                    net_buy_ratio=result.net_buy_ratio,
                    consecutive_streak=result.consecutive_streak,
                    vwap_discount_pct=result.vwap_discount_pct,
                    rsi=result.rsi,
                    avg_flow_ratio=result.avg_flow_ratio,
                    bb_width_pctile=result.bb_width_pctile,
                    bci_label=result.bci_label,
                    bci_tier1_count=result.bci_tier1_count,
                )
            )
            result.foreign_flow_score_breakdown = evidence_resp.evidence
            result.foreign_flow_score = evidence_resp.evidence.foreign_flow_score
            result.foreign_flow_evidence = ForeignFlowEvidence.from_score_breakdown(
                evidence_resp.evidence,
                net_buy_days=result.net_buy_days,
                total_days=result.total_days,
                vwap_pct=result.vwap_pct,
                longer_term_context={
                    "bci_label": result.bci_label,
                    "bci_tier1_count": result.bci_tier1_count,
                },
            )

            # Phase 2.2: resistance-proximity flag
            if (
                request.resistance_gate_enabled
                and result.nearest_resistance_pct is not None
                and result.nearest_resistance_pct < request.resistance_headroom_min_pct
            ):
                result.resistance_flag = True

            # Phase 3.1: corporate action risk flags (dividend, rights issue, RUPS)
            if self._corp_action_repo is not None:
                from datetime import timedelta

                events = self._corp_action_repo.get_upcoming_events(
                    ticker=result.ticker,
                    from_date=today,
                    to_date=today + timedelta(days=request.ex_date_warning_days),
                )
                for event in events:
                    if event.is_dividend:
                        result.dividend_risk = True
                    elif event.is_rights_issue:
                        result.rights_issue_risk = True
                    elif event.is_rups:
                        result.upcoming_rups.append(event.detail or "RUPS")

            # Phase 3.3: seasonality signal
            if self._seasonality_provider is not None:
                result.seasonal_edge = self._seasonality_provider.get_seasonal_edge(
                    ticker=result.ticker,
                    year=today.year,
                    month=today.month,
                    as_of_date=request.as_of_date,
                )

            # Insider activity: director/commissioner transactions in last 90 days
            insider_txns: list = []
            insider_net_buy_ratio: float | None = None
            if self._insider_provider is not None:
                from datetime import timedelta

                from src.domain.value_objects.insider_transaction import compute_net_buy_ratio

                insider_txns = self._insider_provider.get_insider_transactions(
                    ticker=result.ticker,
                    from_date=today - timedelta(days=self._derived_features.insider_lookback_days),
                    to_date=today,
                    action_type="ALL",
                    as_of_date=request.as_of_date,
                )
                buy_txns = [t for t in insider_txns if t.is_buy]
                if buy_txns:
                    result.insider_buying = True
                    result.recent_insider_buys = [t.label for t in buy_txns[:3]]
                insider_net_buy_ratio = compute_net_buy_ratio(insider_txns)
                if insider_net_buy_ratio is None:
                    insider_net_buy_ratio = 0.0

            # Analyst consensus: aggregated buy/hold/sell + price target
            if self._analyst_provider is not None:
                result.analyst_consensus = self._analyst_provider.get_consensus(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            # Shareholding composition: institutional %, individual %, top holder
            if self._shareholding_provider is not None:
                result.shareholding = self._shareholding_provider.get_composition(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            # Bandar detector: Stockbit's institutional operator accumulation signal
            if self._bandar_provider is not None:
                result.bandar_detector = self._bandar_provider.get_snapshot(
                    ticker=result.ticker,
                    session_date=request.as_of_date,
                )

            # Company fundamentals (skip if already fetched by early gate above)
            if self._fundamentals_provider is not None and not fundamentals_fetched:
                result.fundamentals = self._fundamentals_provider.get_fundamentals(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            if self._ticker_notation_provider is not None:
                result.ticker_notation = self._ticker_notation_provider.get_notation(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )

            # Forward EPS estimates — used in composite score
            if self._forward_estimates_provider is not None:
                result.forward_estimates = self._forward_estimates_provider.get_forward_estimates(
                    ticker=result.ticker,
                    as_of_date=request.as_of_date,
                )
                if (
                    result.forward_estimates is not None
                    and result.forward_estimates.forward_pe is None
                    and result.forward_estimates.forward_eps_1y is not None
                    and result.current_price > Decimal("0")
                ):
                    result.forward_estimates = result.forward_estimates.with_current_price(
                        float(result.current_price)
                    )

            result.insider_net_buy_ratio = insider_net_buy_ratio
            signal_ctx = build_signal_context_from_candidate(
                ticker=result.ticker,
                snapshot_date=today,
                candidate=result,
                signal_engine=self._signal_engine,
            )
            # Flow evidence is built from candidate data already in memory — no
            # extra fetch. SetupEvidence is intentionally absent here: the batch
            # screener does not evaluate named setup patterns per ticker; that
            # happens only in the per-ticker swing workflow. Confidence will be
            # 0.40 (flow group only) until the full workflow enriches it further.
            _flow_ev = None
            try:
                _flow_ev = self._flow_confirmation_builder.build(result, analysis_date=today)
            except Exception:
                pass
            result.signal_assessment = self._signal_engine.evaluate_with_context(
                result.ticker, signal_ctx, flow_confirmation_evidence=_flow_ev
            )
            # Accumulation-lifecycle diagnostic for screen display and persisted
            # observations alike — computed once here and reused by
            # _persist_candidate_observations() to avoid detecting twice.
            result.setup_phase = self._detect_candidate_setup_phase(result, _flow_ev, today)

            if (
                request.min_foreign_flow_score_enabled
                and result.foreign_flow_score < request.min_foreign_flow_score
            ):
                all_results.append((result, "rejected_flow", _flow_ev))
                continue
            if request.min_signal_score_enabled and (
                result.signal_assessment is None
                or result.signal_assessment.assessment.score < request.min_signal_score
            ):
                all_results.append((result, "rejected_signal", _flow_ev))
                continue
            all_results.append((result, "pass", _flow_ev))
            candidates.append(result)

        # Phase 3.2: sector breadth post-processing pass
        if request.sector_breadth_enabled and self._ticker_to_group:
            self._apply_sector_breadth(candidates, request)

        # Phase E (Rec 14): post-screening risk funnel — runs only on survivors,
        # not on all 800+ tickers. Reuses already-loaded fundamentals + bandar
        # data from candidates (Rec 15 data sharing — zero extra provider queries).
        if self._risk_use_case is not None:
            self._run_risk_funnel(candidates, today)

        candidates.sort(key=_screen_sort_key, reverse=True)
        self._persist_candidate_observations(all_results, today, request)

        return AccumulationScreenResponse(
            candidates=candidates,
            screened_at=today,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=skipped,
            provider="stockbit" if uses_stockbit else "idx",
        )

    def _persist_candidate_observations(
        self,
        all_results: list[tuple[AccumulationCandidate, str, FlowConfirmationEvidence | None]],
        snapshot_date: date,
        request: AccumulationScreenRequest,
    ) -> None:
        if self._candidate_observations_repo is None or not all_results:
            return
        try:
            captured_at = datetime.now()
            observations = []
            for c, screen_result, flow_ev in all_results:
                # Reuse the phase already detected in execute() — same candidate,
                # same flow evidence, same snapshot date. Avoids detecting twice.
                setup_phase = c.setup_phase
                strategy_evidence = self._build_candidate_strategy_evidence(
                    c,
                    setup_phase,
                    snapshot_date,
                    request,
                )
                ia_evidence = self._build_candidate_institutional_accumulation_evidence(
                    c,
                    snapshot_date,
                )
                tp_snapshot = self._build_candidate_ticker_profile(c, snapshot_date)
                sc_evidence = self._build_candidate_sector_context(
                    c,
                    snapshot_date,
                    tp_snapshot,
                )
                cq_evidence = self._build_candidate_company_quality_context(
                    c,
                    snapshot_date,
                )
                observations.append(
                    CandidateObservation(
                        ticker=c.ticker,
                        snapshot_date=snapshot_date,
                        captured_at=captured_at,
                        payload=_candidate_observation_payload(
                            c,
                            screen_result=screen_result,
                            flow_ev=flow_ev,
                            setup_phase=setup_phase,
                            strategy_evidence=strategy_evidence,
                            ia_evidence=ia_evidence,
                            tp_snapshot=tp_snapshot,
                            sc_evidence=sc_evidence,
                            cq_evidence=cq_evidence,
                            snapshot_date=snapshot_date,
                            captured_at=captured_at,
                            request=request,
                        ),
                    )
                )
            self._candidate_observations_repo.save_many(observations)
        except Exception as exc:
            logger.warning("Candidate observation persistence unavailable: %s", exc)

    def _build_candidate_strategy_evidence(
        self,
        candidate: "AccumulationCandidate",
        setup_phase: "SetupPhaseSnapshot | None",
        snapshot_date: date,
        request: AccumulationScreenRequest,
    ) -> "StrategyEvidence | None":
        if request.strategy_name is None:
            return None
        try:
            from src.application.services.strategy_evidence_builder import (
                StrategyEvidenceBuilder,
                StrategyEvidenceRequest,
            )

            candles = self._market_repo.get_candles(
                candidate.ticker,
                end_date=snapshot_date,
            )
            return StrategyEvidenceBuilder().build(
                StrategyEvidenceRequest(
                    ticker=candidate.ticker,
                    strategy_name=request.strategy_name,
                    candles=tuple(candles),
                    snapshot_date=snapshot_date,
                    setup_family="accumulation",
                    setup_phase=setup_phase,
                )
            )
        except Exception:
            return None

    def _build_candidate_institutional_accumulation_evidence(
        self,
        candidate: "AccumulationCandidate",
        snapshot_date: date,
    ) -> "InstitutionalAccumulationEvidence | None":
        try:
            from datetime import timedelta

            from src.application.services.institutional_accumulation_evidence_builder import (
                InstitutionalAccumulationEvidenceBuilder,
                InstitutionalAccumulationEvidenceRequest,
            )

            start_date = snapshot_date - timedelta(days=45)
            candles = self._market_repo.get_candles(candidate.ticker, end_date=snapshot_date)
            broker_daily_flows = tuple(
                self._broker_repo.get_broker_daily_flows(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            foreign_flow_points = tuple(
                self._broker_repo.get_foreign_flow_points(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            broker_summaries = tuple(
                self._broker_repo.get_broker_summaries(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            return InstitutionalAccumulationEvidenceBuilder.from_yaml().build(
                InstitutionalAccumulationEvidenceRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    broker_daily_flows=broker_daily_flows,
                    foreign_flow_points=foreign_flow_points,
                    broker_summaries=broker_summaries,
                    bandar_snapshot=candidate.bandar_detector,
                    candles=tuple(candles),
                )
            )
        except Exception:
            return None

    def _build_candidate_ticker_profile(
        self,
        candidate: "AccumulationCandidate",
        snapshot_date: date,
    ) -> "TickerProfileSnapshot | None":
        try:
            from datetime import timedelta
            from decimal import Decimal as _Decimal

            from src.application.services.ticker_profile_classifier import (
                TickerProfileClassifier,
                TickerProfileRequest,
            )

            start_date = snapshot_date - timedelta(days=45)
            candles = self._market_repo.get_candles(candidate.ticker, end_date=snapshot_date)
            broker_daily_flows = tuple(
                self._broker_repo.get_broker_daily_flows(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            broker_summaries = tuple(
                self._broker_repo.get_broker_summaries(
                    candidate.ticker, start_date=start_date, end_date=snapshot_date
                )
            )
            market_cap_idr: _Decimal | None = None
            if candidate.fundamentals is not None and candidate.fundamentals.market_cap_idr is not None:
                market_cap_idr = _Decimal(str(candidate.fundamentals.market_cap_idr))
            sector = (
                candidate.ticker_notation.sector
                if candidate.ticker_notation is not None
                else None
            )
            sub_sector = (
                candidate.ticker_notation.sub_sector
                if candidate.ticker_notation is not None
                else None
            )
            return TickerProfileClassifier.from_yaml().classify(
                TickerProfileRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    candles=tuple(candles),
                    broker_daily_flows=broker_daily_flows,
                    broker_summaries=broker_summaries,
                    market_cap_idr=market_cap_idr,
                    sector=sector,
                    sub_sector=sub_sector,
                )
            )
        except Exception:
            return None

    def _build_candidate_sector_context(
        self,
        candidate: "AccumulationCandidate",
        snapshot_date: date,
        tp_snapshot: "TickerProfileSnapshot | None",
    ) -> "SectorContextEvidence | None":
        try:
            from src.application.services.sector_context_evidence_builder import (
                SectorContextEvidenceBuilder,
                SectorContextRequest,
            )

            builder = SectorContextEvidenceBuilder.from_yaml()
            sector = (
                candidate.ticker_notation.sector
                if candidate.ticker_notation is not None
                else None
            ) or (tp_snapshot.sector if tp_snapshot is not None else None)
            peer_tickers = builder.peers_for_ticker(candidate.ticker)
            peer_candles: dict[str, list] = {}
            for peer in peer_tickers:
                try:
                    candles = self._market_repo.get_candles(peer, end_date=snapshot_date)
                    if candles:
                        peer_candles[peer] = list(candles)
                except Exception:
                    pass
            ticker_candles = tuple(
                self._market_repo.get_candles(candidate.ticker, end_date=snapshot_date)
            )
            ihsg_20d_return = _simple_return(
                self._market_repo.get_candles("IHSG", end_date=snapshot_date),
                lookback=20,
                min_valid=18,
            )
            return builder.build(
                SectorContextRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    sector=sector,
                    ticker_candles=ticker_candles,
                    peer_candles=peer_candles,
                    ihsg_20d_return=ihsg_20d_return,
                )
            )
        except Exception:
            return None

    def _build_candidate_company_quality_context(
        self,
        candidate: "AccumulationCandidate",
        snapshot_date: date,
    ) -> "CompanyQualityContextEvidence | None":
        """Build DIAGNOSTIC company-quality / ticker-alpha conviction evidence.

        Uses enrichment already loaded on the candidate (forward P/E, analyst,
        insider, seasonality) via the shared SignalContext builder — no extra
        provider fetch. Zero scoring authority (DIAGNOSTIC).
        """
        if self._signal_engine is None:
            return None
        try:
            from src.application.services.company_quality_context_evidence_builder import (
                CompanyQualityContextEvidenceBuilder,
                CompanyQualityContextRequest,
            )

            signal_ctx = build_signal_context_from_candidate(
                ticker=candidate.ticker,
                snapshot_date=snapshot_date,
                candidate=candidate,
                signal_engine=self._signal_engine,
            )
            return CompanyQualityContextEvidenceBuilder.from_yaml().build(
                CompanyQualityContextRequest(
                    ticker=candidate.ticker,
                    snapshot_date=snapshot_date,
                    signal_context=signal_ctx,
                )
            )
        except Exception:
            return None

    def _detect_candidate_setup_phase(
        self,
        candidate: "AccumulationCandidate",
        flow_ev: "FlowConfirmationEvidence | None",
        snapshot_date: date,
    ) -> "SetupPhaseSnapshot | None":
        try:
            from src.application.services.candle_provenance import resolve_candle_source
            from src.application.services.setup_evidence_builder import (
                SetupEvidenceBuilder,
            )
            from src.application.services.setup_phase_detector import SetupPhaseDetector
            from src.application.services.setup_phase_history import (
                load_previous_setup_phases,
            )

            candles = self._market_repo.get_candles(
                candidate.ticker,
                end_date=snapshot_date,
            )
            previous_phases = load_previous_setup_phases(
                self._candidate_observations_repo,
                ticker=candidate.ticker,
                before_date=snapshot_date,
                setup_family="accumulation",
            )
            candle_source = resolve_candle_source(
                self._market_repo,
                ticker=candidate.ticker,
                as_of_date=candles[-1].date if candles else snapshot_date,
            )
            setup_evidence = SetupEvidenceBuilder().build(
                candidate,
                None,
                rs_vs_ihsg_5d=None,
                volume_trend_ratio=None,
                candle_source=candle_source,
                analysis_date=snapshot_date,
            )
            return SetupPhaseDetector().detect(
                candles=candles,
                setup_eval=None,
                setup_evidence=setup_evidence,
                flow_evidence=flow_ev,
                setup_family="accumulation",
                previous_phases=previous_phases,
            )
        except Exception:
            return None

    def _run_risk_funnel(
        self,
        candidates: list[AccumulationCandidate],
        as_of_date: date,
    ) -> None:
        """Run AssessRiskUseCase on each survivor and attach the result in-place.

        Builds GateContext from already-loaded candidate data — no duplicate
        provider calls (Rec 15: share data snapshots).
        """
        from src.application.use_case.assess_risk_use_case import AssessRiskRequest
        from src.application.use_case.assess_trade_setup_use_case import (
            AssessTradeSetupRequest,
            AssessTradeSetupUseCase,
        )
        from src.domain.rules.risk_gate import GateContext

        trade_setup_uc = AssessTradeSetupUseCase()

        for candidate in candidates:
            try:
                gate_ctx = GateContext(
                    ticker=candidate.ticker,
                    snapshot_date=as_of_date,
                    piotroski_f_score=(
                        candidate.fundamentals.piotroski_f_score if candidate.fundamentals else None
                    ),
                    market_cap_idr=(
                        candidate.fundamentals.market_cap_idr if candidate.fundamentals else None
                    ),
                    free_float_pct=(
                        candidate.shareholding.free_float_pct
                        if candidate.shareholding is not None
                        else None
                    ),
                    five_day_accdist=(
                        candidate.bandar_detector.five_day_accdist
                        if candidate.bandar_detector
                        else None
                    ),
                )
                resp = self._risk_use_case.execute(  # type: ignore[union-attr]
                    AssessRiskRequest(
                        ticker=candidate.ticker,
                        gate_context=gate_ctx,
                    )
                )
                candidate.risk_assessment = resp.assessment
                if candidate.signal_assessment is not None:
                    try:
                        trade_resp = trade_setup_uc.execute(
                            AssessTradeSetupRequest(
                                ticker=candidate.ticker,
                                snapshot_date=as_of_date,
                                signal_response=candidate.signal_assessment,
                                risk_response=resp,
                            )
                        )
                        candidate.trade_setup = trade_resp.setup
                    except Exception as exc2:
                        logger.debug(
                            "Risk funnel: trade_setup failed for %s: %s", candidate.ticker, exc2
                        )
            except Exception as exc:
                logger.debug("Risk funnel: assessment failed for %s: %s", candidate.ticker, exc)

    def _evaluate_ticker(
        self,
        ticker: str,
        window_days: int,
        today: date,
        min_net_buy_days: int,
        rsi_period: int,
        sma_period: int,
        tier1_broker_codes: frozenset[str] = TIER1_FOREIGN_BROKERS,
        bci_cluster_min_count: int = 3,
        bci_stable_min_count: int = 1,
    ) -> AccumulationCandidate | None:
        """Compute accumulation metrics for one ticker."""
        # Load all broker rows up to as_of_date, then select the latest N
        # broker sessions. Calendar-day cutoffs distort IDX windows around
        # weekends, holidays, and data-lag days.
        summaries = self._broker_repo.get_broker_summaries(
            ticker=ticker,
            start_date=None,
            end_date=today,
        )

        if not summaries:
            return None

        summaries = [s for s in summaries if _is_usable_broker_summary(s)]
        if not summaries:
            return None

        window_summaries = sorted(summaries, key=lambda s: s.date)[-window_days:]

        if len(window_summaries) < min_net_buy_days:
            return None

        # Core accumulation metrics
        net_buy_days = sum(1 for s in window_summaries if s.is_foreign_accumulating)
        total_days = len(window_summaries)
        net_buy_ratio = net_buy_days / total_days if total_days > 0 else 0.0
        total_net_value = sum((s.foreign_net_value for s in window_summaries), Decimal("0"))

        # Consecutive buy streak (counting backwards from most recent)
        streak = 0
        for s in sorted(window_summaries, key=lambda x: x.date, reverse=True):
            if s.is_foreign_accumulating:
                streak += 1
            else:
                break

        # Foreign VWAP
        total_buy_value = sum((s.foreign_buy_value for s in window_summaries), Decimal("0"))
        total_buy_lots = sum(s.foreign_buy_lot for s in window_summaries)
        foreign_vwap: Decimal | None = None
        if total_buy_lots > 0:
            try:
                foreign_vwap = (total_buy_value / (total_buy_lots * SHARES_PER_LOT)).quantize(
                    Decimal("0.01")
                )
            except InvalidOperation:
                foreign_vwap = None

        # Avg foreign flow ratio (% of total daily turnover, already in BrokerSummary)
        flow_ratios = [float(s.foreign_flow_ratio) for s in window_summaries if s.total_value > 0]
        avg_flow_ratio = sum(flow_ratios) / len(flow_ratios) if flow_ratios else None

        latest_broker_date = window_summaries[-1].date if window_summaries else None

        # Load candles for price + RSI + trend + BB squeeze
        candles = self._market_repo.get_candles(ticker, end_date=today)
        if not candles:
            current_price = Decimal("0")
            rsi = None
            trend = "SIDE"
            bb_width = None
            bb_width_pctile = None
            latest_candle_date = None
        else:
            current_price = candles[-1].close
            latest_candle_date = candles[-1].date
            rsi = self._compute_rsi(candles, rsi_period)
            trend = self._compute_trend(candles, sma_period)
            bb_width, bb_width_pctile = self._compute_bb_squeeze(
                candles,
                period=self._derived_features.bb_period,
                history=self._derived_features.bb_history,
            )

        # Phase 2.2: Resistance proximity (MA200 and 52-week high)
        ma200, week52_high, nearest_resistance_pct = self._compute_resistance(
            candles, current_price
        )

        # Foreign VWAP discount % — how far foreigners' avg buy is above current price
        vwap_discount_pct = foreign_vwap_discount_pct(foreign_vwap, current_price)

        # Market VWAP % — how far current price is from 20-day all-participant VWAP
        # Negative = price below VWAP (constructive; entering below market average cost basis)
        vwap_pct: float | None = None
        if candles:
            try:
                vwap_window = candles[-self._derived_features.market_vwap_period :]
                total_vol = sum(c.volume for c in vwap_window)
                if total_vol > 0:
                    total_tpv = sum(
                        (c.high + c.low + c.close) / Decimal("3") * c.volume for c in vwap_window
                    )
                    market_vwap = total_tpv / total_vol
                    if market_vwap > 0:
                        vwap_pct = float((current_price - market_vwap) / market_vwap * 100)
            except (InvalidOperation, ZeroDivisionError):
                pass

        # Granular broker info from per-day broker_daily_flow (Stockbit only).
        # These are real daily rows — never period aggregates.
        top_brokers: list[str] | None = None
        institutional_flag = False
        bci_label: str | None = None
        bci_tier1_count: int = 0

        daily_flows = self._broker_repo.get_broker_daily_flows(
            ticker=ticker,
            end_date=today,
        )
        if daily_flows:
            # Collect the window dates from broker summaries to align the window
            window_dates = {s.date for s in window_summaries}
            window_flows = [f for f in daily_flows if f.date in window_dates]

            if window_flows:
                # Aggregate net_lot per broker across the window
                from collections import defaultdict

                broker_net: dict[str, int] = defaultdict(int)
                for f in window_flows:
                    broker_net[f.broker_code] += f.net_lot

                net_buyers = sorted(
                    [(code, net) for code, net in broker_net.items() if net > 0],
                    key=lambda x: x[1],
                    reverse=True,
                )
                if net_buyers:
                    top_brokers = [code for code, _ in net_buyers[:5]]
                    # BCI: count all Tier 1 codes among any net-buyers (not just top 5)
                    all_net_buyer_codes = {code for code, _ in net_buyers}
                    bci_tier1_count = len(all_net_buyer_codes & tier1_broker_codes)
                    if bci_tier1_count >= bci_cluster_min_count:
                        bci_label = BCI_CLUSTER
                    elif bci_tier1_count >= bci_stable_min_count:
                        bci_label = BCI_STABLE
                    else:
                        bci_label = BCI_RETAIL
                    institutional_flag = bci_tier1_count > 0

        return AccumulationCandidate(
            ticker=ticker,
            window_days=window_days,
            net_buy_days=net_buy_days,
            total_days=total_days,
            net_buy_ratio=net_buy_ratio,
            total_net_value=total_net_value,
            consecutive_streak=streak,
            foreign_vwap=foreign_vwap,
            current_price=current_price,
            vwap_discount_pct=vwap_discount_pct,
            rsi=rsi,
            trend=trend,
            foreign_flow_score=0.0,  # populated later by ScoreForeignFlowUseCase
            top_brokers=top_brokers,
            institutional_flag=institutional_flag,
            bci_label=bci_label,
            bci_tier1_count=bci_tier1_count,
            vwap_pct=vwap_pct,
            avg_flow_ratio=avg_flow_ratio,
            bb_width=bb_width,
            bb_width_pctile=bb_width_pctile,
            ma200=ma200,
            week52_high=week52_high,
            nearest_resistance_pct=nearest_resistance_pct,
            latest_candle_date=latest_candle_date,
            latest_broker_date=latest_broker_date,
        )

    def _apply_sector_breadth(
        self,
        candidates: list[AccumulationCandidate],
        request: AccumulationScreenRequest,
    ) -> None:
        """Post-processing: compute sector breadth and apply bonus in-place.

        Groups candidates by idx_groups mapping. For groups with enough members
        (>= min_tickers_for_breadth), computes the fraction with net_buy_ratio > 0.
        Applies sector_breadth_bonus_pts to ALL members of qualifying groups.
        """
        from collections import defaultdict

        # Group candidates by their idx_groups group
        group_candidates: dict[str, list[AccumulationCandidate]] = defaultdict(list)
        for candidate in candidates:
            group = self._ticker_to_group.get(candidate.ticker.upper())
            if group:
                group_candidates[group].append(candidate)

        # For each group with enough members, compute breadth and apply bonus
        for group, members in group_candidates.items():
            if len(members) < request.sector_breadth_min_tickers:
                # Set breadth_pct but no bonus (insufficient sample)
                total = len(members)
                positive = sum(1 for m in members if m.net_buy_ratio > 0)
                breadth_pct = positive / total if total > 0 else 0.0
                for m in members:
                    m.sector_breadth_pct = breadth_pct
                continue

            positive = sum(1 for m in members if m.net_buy_ratio > 0)
            breadth_pct = positive / len(members)

            for m in members:
                m.sector_breadth_pct = breadth_pct
                if breadth_pct >= request.sector_breadth_threshold:
                    m.foreign_flow_score += request.sector_breadth_bonus_pts
                    m.sector_breadth_bonus = request.sector_breadth_bonus_pts

    def _compute_rsi(self, candles: list, period: int) -> float | None:
        """Wilder's RSI from candle close prices."""
        closes = [float(c.close) for c in candles]
        if len(closes) < period + 1:
            return None

        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))

        # Initial averages (SMA seed)
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's smoothing for the rest
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _compute_trend(self, candles: list, sma_period: int) -> str:
        """Classify trend relative to SMA."""
        if len(candles) < sma_period:
            return "SIDE"

        recent = candles[-sma_period:]
        sma = sum(float(c.close) for c in recent) / sma_period
        current = float(candles[-1].close)
        pct_diff = (current - sma) / sma * 100

        threshold = self._derived_features.trend_threshold_pct
        if pct_diff > threshold:
            return "UP"
        elif pct_diff < -threshold:
            return "DOWN"
        return "SIDE"

    @staticmethod
    def _compute_bb_widths(candles: list, period: int = 20) -> list[float]:
        """BB Width = (upper - lower) / mid * 100 for each candle."""
        closes = [float(c.close) for c in candles]
        if len(closes) < period:
            return []
        out = []
        for i in range(period - 1, len(closes)):
            window = closes[i - period + 1 : i + 1]
            mid = sum(window) / period
            if mid <= 0:
                out.append(0.0)
                continue
            std = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
            out.append(4.0 * std / mid * 100)  # (upper-lower)/mid*100, upper=mid+2σ
        return out

    def _compute_bb_squeeze(
        self, candles: list, period: int = 20, history: int = 60
    ) -> tuple[float | None, float | None]:
        """Return (bb_width_now, percentile_rank_vs_last_N_days).

        percentile=0.0 means current width is the tightest in `history` days
        (maximum squeeze). percentile=1.0 means widest (expanding volatility).
        """
        widths = self._compute_bb_widths(candles, period)
        if not widths:
            return None, None
        bb_width_now = widths[-1]
        if len(widths) < history:
            return bb_width_now, None
        recent = widths[-history:]
        rank = sum(1 for w in recent if w <= bb_width_now) / len(recent)
        return bb_width_now, rank

    def _compute_resistance(
        self,
        candles: list,
        current_price: Decimal,
    ) -> tuple[Decimal | None, Decimal | None, float | None]:
        """Compute MA200, 52-week high, and % distance to nearest resistance above price.

        Returns (ma200, week52_high, nearest_resistance_pct).
        nearest_resistance_pct is None if no resistance level is above current price.
        Positive value = resistance is X% above current price (more headroom = better).
        """
        if not candles or current_price <= 0:
            return None, None, None

        ma200: Decimal | None = None
        ma_period = self._derived_features.resistance_ma_period
        if len(candles) >= ma_period:
            ma200 = Decimal(str(sum(c.close for c in candles[-ma_period:]) / ma_period))

        week52_high: Decimal | None = None
        if len(candles) >= 1:
            week52_high = max(
                c.high for c in candles[-self._derived_features.resistance_high_period :]
            )

        resistances: list[float] = []
        for level in (ma200, week52_high):
            if level is not None and level > current_price:
                pct = float((level - current_price) / current_price * 100)
                resistances.append(pct)

        nearest_resistance_pct = min(resistances) if resistances else None
        return ma200, week52_high, nearest_resistance_pct


def compute_percent_plan(
    entry: "Decimal",
    stop_pct: "Decimal",
    target_pct: "Decimal",
) -> "tuple[Decimal, Decimal]":
    """Compute stop and target prices from a percentage plan."""
    stop = entry * (Decimal("1") - stop_pct / Decimal("100"))
    target = entry * (Decimal("1") + target_pct / Decimal("100"))
    return stop, target


def classify_multi_window_pattern(
    windows: list[int],
    candidates_by_window: dict[int, "AccumulationCandidate | None"],
    coiled_spring_min_score: float,
    coiled_spring_bb_pctile: float,
) -> str:
    """
    Label the multi-window accumulation pattern for a single ticker.

    Returns one of: "coiled spring", "sustained", "building",
    "fresh rotation", "long-term only", "mixed", "weak"
    """
    hot = [
        w
        for w in windows
        if candidates_by_window.get(w)
        and candidates_by_window[w].foreign_flow_score >= coiled_spring_min_score
    ]

    for w in windows:
        c = candidates_by_window.get(w)
        if (
            c
            and c.foreign_flow_score >= coiled_spring_min_score
            and c.bb_width_pctile is not None
            and c.bb_width_pctile <= coiled_spring_bb_pctile
        ):
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"
