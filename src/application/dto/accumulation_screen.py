"""DTOs and serialization contracts for the accumulation screener."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from src.domain.value_objects.accum_score_breakdown import AccumScoreBreakdown
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence

if TYPE_CHECKING:
    from src.application.dto.accumulation_structural_filter import (
        StructuralFilterDecision,
    )
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.domain.value_objects.analyst_consensus import AnalystConsensus
    from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
    from src.domain.value_objects.company_fundamentals import CompanyFundamentals
    from src.domain.value_objects.data_freshness_status import DataFreshnessStatus
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.forward_estimates import ForwardEstimates
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.risk_assessment import RiskAssessment
    from src.domain.value_objects.risk_gate_audit import (
        GateContextCompleteness,
        GateEvaluationRecord,
    )
    from src.domain.value_objects.seasonal_edge import SeasonalEdge
    from src.domain.value_objects.sector_macro_context_evidence import (
        SectorMacroContextEvidence,
    )
    from src.domain.value_objects.setup_evaluation import SetupEvaluation
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.shareholding_composition import ShareholdingComposition
    from src.domain.value_objects.ticker_notation import TickerNotationSnapshot
    from src.domain.value_objects.trade_setup import TradeSetup


# Tier 1 — pure foreign institutional desks (custodian + prime brokerage).
# These are the codes whose net_lot signal most reliably tracks foreign institutional intent.
# YP (Indo Premier / Mirae) is domestic and excluded here even though it's in
# _INSTITUTIONAL_PROXY_CODES for flow aggregation — it doesn't signal foreign custody.
TIER1_FOREIGN_BROKERS = frozenset({"AK", "BK", "ZP", "KZ", "YU", "RX", "HD", "CP", "DR"})


@dataclass
class AccumulationScreenRequest:
    """Input parameters for the screener."""

    tickers: list[str]
    window_days: int = 7  # latest broker sessions: 7, 30, or 90
    min_net_buy_days: int = 2  # skip tickers with fewer qualifying days
    min_accum_score: float = 0.0  # filter: only include accum_score >= this
    min_accum_score_enabled: bool = True
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
    # market_context feeds DecisionPolicy (regime floors / authority caps) when
    # supplied on observation-capture and screen paths. It is also persisted
    # into candidate observation fingerprints for attribution. Omitting it
    # keeps legacy RISK_ON DecisionPolicy defaults (regime=null on constraints).
    market_context: "MarketContext | None" = None

    def __init__(
        self,
        tickers: list[str],
        window_days: int = 7,
        min_net_buy_days: int = 2,
        min_accum_score: float = 0.0,
        min_accum_score_enabled: bool = True,
        min_signal_score: float = 0.0,
        min_signal_score_enabled: bool = False,
        rsi_period: int | None = None,
        sma_period: int | None = None,
        as_of_date: date | None = None,
        resistance_gate_enabled: bool = True,
        resistance_headroom_min_pct: float = 5.0,
        regime: str | None = None,
        ex_date_warning_days: int = 10,
        tier1_broker_codes: frozenset[str] | None = None,
        bci_cluster_min_count: int = 3,
        bci_stable_min_count: int = 1,
        min_market_cap_idr: int = 0,
        min_piotroski: int = 0,
        strategy_name: str | None = None,
        # market_context is observation-attribution only for screen accum. It is
        # persisted into candidate observation fingerprints. It must not affect
        # screen scoring/verdict without an explicit behavior-change task.
        market_context: "MarketContext | None" = None,
    ) -> None:
        self.tickers = tickers
        self.window_days = window_days
        self.min_net_buy_days = min_net_buy_days
        self.min_accum_score = min_accum_score
        self.min_accum_score_enabled = min_accum_score_enabled
        self.min_signal_score = min_signal_score
        self.min_signal_score_enabled = min_signal_score_enabled
        self.rsi_period = rsi_period
        self.sma_period = sma_period
        self.as_of_date = as_of_date
        self.resistance_gate_enabled = resistance_gate_enabled
        self.resistance_headroom_min_pct = resistance_headroom_min_pct
        self.regime = regime
        self.ex_date_warning_days = ex_date_warning_days
        self.tier1_broker_codes = tier1_broker_codes or TIER1_FOREIGN_BROKERS
        self.bci_cluster_min_count = bci_cluster_min_count
        self.bci_stable_min_count = bci_stable_min_count
        self.min_market_cap_idr = min_market_cap_idr
        self.min_piotroski = min_piotroski
        self.strategy_name = strategy_name
        self.market_context = market_context


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
    accum_score: float  # 0-100 accumulation evidence score (ADR-043)
    top_brokers: list[str] | None  # per-broker codes (Stockbit only)
    institutional_flag: bool  # True if major institutional broker present
    # Improvement #1: flow ratio signal
    avg_flow_ratio: float | None = None  # avg % of daily turnover that's foreign
    accum_score_breakdown: AccumScoreBreakdown | None = None
    foreign_flow_evidence: ForeignFlowEvidence | None = None
    # Improvement #3: BB squeeze
    bb_width: float | None = None  # current BB Width %
    bb_width_pctile: float | None = None  # 0..1 vs last 60 days (lower = tighter)
    # BCI — Broker Concentration Index
    bci_label: str | None = None  # "CLUSTER" | "STABLE" | "RETAIL-LED" | None
    bci_tier1_count: int = 0  # distinct Tier 1 foreign desks in net-buyers
    # Diagnostic only (Stage 1): Tier-1 net-buy IDR among lot-based net buyers, and
    # absorption vs aggregate foreign net when aggregate is selling. Never scored.
    bci_tier1_net_value: Decimal | None = None
    bci_absorption_ratio: float | None = None
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
    # Data currency — dates of the most recent loaded records; None if no data
    latest_candle_date: date | None = None
    latest_broker_date: date | None = None
    # Max date among broker_daily_flow rows actually consumed for BCI/
    # top_brokers (a subset of the broker_summaries window; see
    # AccumulationCandidateEvaluator.evaluate). None if no daily-flow row
    # fell inside that window.
    latest_broker_daily_flow_date: date | None = None
    # Forward EPS/Revenue estimates (Stockbit analyst consensus endpoint)
    forward_estimates: "ForwardEstimates | None" = None
    # Accumulation-discovery signal assessment
    signal_assessment: "AssessSignalResponse | None" = None
    # Phase E: post-screening risk assessment (populated by risk funnel when configured)
    risk_assessment: "RiskAssessment | None" = None
    # Package C2 audit attached by risk funnel — child JSON only, not lean payload
    risk_gate_evaluations: tuple[GateEvaluationRecord, ...] | None = None
    risk_gate_context_completeness: GateContextCompleteness | None = None
    # Unified trade action verdict — requires both signal_assessment and risk funnel
    trade_setup: "TradeSetup | None" = None
    # Accumulation-lifecycle diagnostic (ACCUMULATION/COMPRESSION/BREAKOUT_CONFIRMATION/
    # EXHAUSTION/DISTRIBUTION/FAILED/NONE); None when detection is unavailable or fails.
    setup_phase: "SetupPhaseSnapshot | None" = None
    # HIGH-2: resolved exactly once in AccumulationCandidateSignalAssessor —
    # the same family passed to SignalEngine.evaluate_accumulation_discovery() and to
    # setup_phase detection. Persistence reuses this verbatim; it must never
    # be recomputed with strategy_evidence after scoring.
    setup_family_result: "PrimarySetupFamilyResult | None" = None
    # Schema v8: every AVAILABLE_SWING_SETUPS evaluation at screen time
    # (broker_detail=None on discovery). Diagnostic/research only — does not
    # grant entry authority. Persistence serializes a lean fingerprint view;
    # family resolution reuses these evals (MATCH-only) without re-running.
    named_setup_evaluations: "dict[str, SetupEvaluation] | None" = None
    # Market-calendar-aware freshness/alignment (S3); None until the screen
    # accum projector computes it — table and JSON both render this field.
    freshness: "DataFreshnessStatus | None" = None
    # ADR-053 / P2a DIAGNOSTIC — attached on single-ticker judgment desk only
    # (saham screen accum TICKER). Not used by Signal/Risk/TradeSetup scoring.
    sector_macro_context_evidence: "SectorMacroContextEvidence | None" = None

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
            "vwap_discount_pct": (
                round(self.vwap_discount_pct, 2) if self.vwap_discount_pct is not None else None
            ),
            "rsi": round(self.rsi, 2) if self.rsi is not None else None,
            "trend": self.trend,
            "accum_score": self.accum_score,
            "top_brokers": self.top_brokers,
            "institutional_flag": self.institutional_flag,
            "bci_label": self.bci_label,
            "bci_tier1_count": self.bci_tier1_count,
            "bci_tier1_net_value": (
                str(self.bci_tier1_net_value) if self.bci_tier1_net_value is not None else None
            ),
            "bci_absorption_ratio": (
                round(self.bci_absorption_ratio, 4)
                if self.bci_absorption_ratio is not None
                else None
            ),
            "vwap_pct": round(self.vwap_pct, 2) if self.vwap_pct is not None else None,
            "avg_flow_ratio": (
                round(self.avg_flow_ratio, 2) if self.avg_flow_ratio is not None else None
            ),
            "accum_score_breakdown": (
                self.accum_score_breakdown.to_dict()
                if self.accum_score_breakdown is not None
                else None
            ),
            "foreign_flow_evidence": (
                self.foreign_flow_evidence.to_dict()
                if self.foreign_flow_evidence is not None
                else None
            ),
            "bb_width": round(self.bb_width, 2) if self.bb_width is not None else None,
            "bb_width_pctile": (
                round(self.bb_width_pctile, 3) if self.bb_width_pctile is not None else None
            ),
            "dividend_risk": self.dividend_risk,
            "rights_issue_risk": self.rights_issue_risk,
            "upcoming_rups": self.upcoming_rups,
            "seasonal_score": round(self.seasonal_edge.score, 2) if self.seasonal_edge else None,
            "seasonal_label": self.seasonal_edge.label if self.seasonal_edge else None,
            "insider_buying": self.insider_buying,
            "recent_insider_buys": self.recent_insider_buys,
            "insider_net_buy_ratio": (
                round(self.insider_net_buy_ratio, 4)
                if self.insider_net_buy_ratio is not None
                else None
            ),
            "analyst_consensus": (
                self.analyst_consensus.to_dict() if self.analyst_consensus else None
            ),
            "shareholding": self.shareholding.to_dict() if self.shareholding else None,
            "bandar_detector": self.bandar_detector.to_dict() if self.bandar_detector else None,
            "fundamentals": self.fundamentals.to_dict() if self.fundamentals else None,
            "ticker_notation": self.ticker_notation.to_dict() if self.ticker_notation else None,
            "latest_candle_date": (
                self.latest_candle_date.isoformat() if self.latest_candle_date else None
            ),
            "latest_broker_date": (
                self.latest_broker_date.isoformat() if self.latest_broker_date else None
            ),
            "latest_broker_daily_flow_date": (
                self.latest_broker_daily_flow_date.isoformat()
                if self.latest_broker_daily_flow_date
                else None
            ),
            "forward_estimates": (
                self.forward_estimates.to_dict() if self.forward_estimates else None
            ),
            "signal_assessment": (
                {
                    "identity": self.signal_assessment.assessment.identity.to_dict(),
                    "score": self.signal_assessment.assessment.score,
                    "strength": self.signal_assessment.assessment.strength.value,
                    "entry_quality": self.signal_assessment.assessment.entry_quality.value,
                    "breakdown": self.signal_assessment.assessment.breakdown_dict,
                    "signal_authority_coverage": (
                        self.signal_assessment.assessment.signal_authority_coverage
                    ),
                    "setup_readiness": (
                        self.signal_assessment.setup_readiness.to_dict()
                        if self.signal_assessment.setup_readiness
                        else None
                    ),
                    "coverage_warning": self.signal_assessment.coverage_warning,
                    "decision_constraints": (
                        self.signal_assessment.assessment.decision_constraints.to_dict()
                        if self.signal_assessment.assessment.decision_constraints
                        else None
                    ),
                }
                if self.signal_assessment
                else None
            ),
            "risk_status": self.risk_assessment.risk_level_name if self.risk_assessment else None,
            "risk_confidence": self.risk_assessment.confidence if self.risk_assessment else None,
            "risk_gate": self.risk_assessment.gate_triggered if self.risk_assessment else None,
            # Composed judgment (ADR-054 S1): same TradeSetup memory field as the table Action.
            "trade_setup": self.trade_setup.to_dict() if self.trade_setup is not None else None,
            "setup_phase": self.setup_phase.to_dict() if self.setup_phase else None,
            # Pattern recognition already computed at screen time (diagnostic).
            # Primary family + named setup MATCH/PARTIAL/NO_MATCH — not entry authority.
            "setup_family_result": (
                self.setup_family_result.to_dict() if self.setup_family_result is not None else None
            ),
            "named_setup_evaluations": (
                {
                    name: evaluation.to_dict()
                    for name, evaluation in self.named_setup_evaluations.items()
                }
                if self.named_setup_evaluations
                else None
            ),
            "freshness": self.freshness.to_dict() if self.freshness else None,
            "sector_macro_context_evidence": (
                self.sector_macro_context_evidence.to_dict()
                if self.sector_macro_context_evidence is not None
                else None
            ),
        }


@dataclass(frozen=True)
class AccumulationCandidateEvaluationResult:
    """`AccumulationCandidateEvaluator.evaluate()`'s candidate plus the exact
    rows consumed to compute it (ADR-041 CANONICAL-EVIDENCE-BOUNDARY).

    Every tuple here is the same bounded, future/ticker-filtered data
    `evaluate()` itself used for the candidate's fields — never a superset
    of fetched-but-unused rows, and never re-fetched by a caller.
    """

    candidate: AccumulationCandidate
    consumed_candles: tuple  # tuple[Candle, ...]
    consumed_broker_summaries: tuple  # tuple[BrokerSummary, ...]
    consumed_broker_daily_flows: tuple  # tuple[BrokerDailyFlow, ...]
    analysis_date: date

    def __post_init__(self) -> None:
        for row in self.consumed_candles:
            if row.ticker != self.candidate.ticker:
                raise ValueError(
                    f"AccumulationCandidateEvaluationResult consumed_candles ticker "
                    f"mismatch: candidate.ticker={self.candidate.ticker!r}, "
                    f"row.ticker={row.ticker!r}"
                )
            if row.date > self.analysis_date:
                raise ValueError(
                    f"AccumulationCandidateEvaluationResult consumed_candles has a "
                    f"row dated {row.date!r} after analysis_date={self.analysis_date!r}"
                )
        for row in self.consumed_broker_summaries:
            if row.ticker != self.candidate.ticker:
                raise ValueError(
                    f"AccumulationCandidateEvaluationResult consumed_broker_summaries "
                    f"ticker mismatch: candidate.ticker={self.candidate.ticker!r}, "
                    f"row.ticker={row.ticker!r}"
                )
            if row.date > self.analysis_date:
                raise ValueError(
                    f"AccumulationCandidateEvaluationResult consumed_broker_summaries "
                    f"has a row dated {row.date!r} after analysis_date="
                    f"{self.analysis_date!r}"
                )
        for row in self.consumed_broker_daily_flows:
            if row.ticker != self.candidate.ticker:
                raise ValueError(
                    f"AccumulationCandidateEvaluationResult consumed_broker_daily_flows "
                    f"ticker mismatch: candidate.ticker={self.candidate.ticker!r}, "
                    f"row.ticker={row.ticker!r}"
                )
            if row.date > self.analysis_date:
                raise ValueError(
                    f"AccumulationCandidateEvaluationResult consumed_broker_daily_flows "
                    f"has a row dated {row.date!r} after analysis_date="
                    f"{self.analysis_date!r}"
                )

        max_candle_date = max((row.date for row in self.consumed_candles), default=None)
        if self.candidate.latest_candle_date != max_candle_date:
            raise ValueError(
                f"AccumulationCandidateEvaluationResult candidate.latest_candle_date="
                f"{self.candidate.latest_candle_date!r} disagrees with max consumed "
                f"candle date={max_candle_date!r}"
            )
        max_broker_date = max((row.date for row in self.consumed_broker_summaries), default=None)
        if self.candidate.latest_broker_date != max_broker_date:
            raise ValueError(
                f"AccumulationCandidateEvaluationResult candidate.latest_broker_date="
                f"{self.candidate.latest_broker_date!r} disagrees with max consumed "
                f"broker-summary date={max_broker_date!r}"
            )
        max_daily_flow_date = max(
            (row.date for row in self.consumed_broker_daily_flows), default=None
        )
        if self.candidate.latest_broker_daily_flow_date != max_daily_flow_date:
            raise ValueError(
                f"AccumulationCandidateEvaluationResult "
                f"candidate.latest_broker_daily_flow_date="
                f"{self.candidate.latest_broker_daily_flow_date!r} disagrees with max "
                f"consumed broker-daily-flow date={max_daily_flow_date!r}"
            )


@dataclass(frozen=True)
class AccumulationScreenObservationCandidate:
    """One evaluated ticker paired with its screen outcome and flow evidence.

    Covers survivors and rejected candidates alike — rejected records are
    learnable negative samples. Internal application-layer detail: exists so
    an explicit recording use case can persist observations from an
    already-computed AccumulationScreenResponse without re-running the screen.

    Owns `evaluation_result` — the exact `AccumulationCandidateEvaluationResult`
    the evaluator returned for this ticker (ADR-041 CANONICAL-EVIDENCE-BOUNDARY)
    — as the single source of truth for the candidate. There is deliberately no
    independent `candidate` field: one could disagree with
    `evaluation_result.candidate` (e.g. after later enrichment mutates the
    candidate but not a separately-held reference). `candidate` mutates in
    place through the screen pipeline (structural filter, enrichment, signal
    assessment all mutate and return the same object the evaluator produced),
    so `evaluation_result.candidate` always reflects the final, fully-enriched
    candidate without needing to be reconstructed.
    """

    evaluation_result: AccumulationCandidateEvaluationResult
    screen_result: str
    flow_evidence: "FlowConfirmationEvidence | None"
    structural_filter_decision: "StructuralFilterDecision | None" = None

    @property
    def candidate(self) -> AccumulationCandidate:
        return self.evaluation_result.candidate


@dataclass
class AccumulationScreenResponse:
    """Screener output."""

    candidates: list[AccumulationCandidate]  # sorted by foreign-flow score descending
    screened_at: date
    window_days: int
    total_tickers_checked: int
    tickers_skipped: int  # insufficient data
    provider: str  # "idx" or "stockbit"
    # Every evaluated ticker — survivors and rejected alike. Empty unless the
    # caller wants it; screen execution itself never reads or acts on this
    # field (read-only contract) — it exists only for an explicit recording
    # use case to consume.
    observation_candidates: list[AccumulationScreenObservationCandidate] = field(
        default_factory=list
    )
