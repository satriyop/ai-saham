"""
AccumulationScreenUseCase — multi-stock foreign accumulation screener.

Scans a list of tickers for sustained foreign investor accumulation patterns.
Foreign-flow evidence scoring is delegated to AssessAccumulationEvidenceUseCase;
this use case owns orchestration, filtering, enrichment, and sorting.

Intraday vs Swing usage:
  This screener produces a SWING WATCHLIST (5–20 day horizon).
  For intraday timing, cross-reference with `saham screen pre-open`.

Layer: Application
Depends on: Domain ports only — no infrastructure imports
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse
    from src.domain.value_objects.analyst_consensus import AnalystConsensus
    from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
    from src.domain.value_objects.company_fundamentals import CompanyFundamentals
    from src.domain.value_objects.forward_estimates import ForwardEstimates
    from src.domain.value_objects.risk_assessment import RiskAssessment
    from src.domain.value_objects.seasonal_edge import SeasonalEdge
    from src.domain.value_objects.shareholding_composition import ShareholdingComposition
    from src.domain.value_objects.ticker_notation import TickerNotationSnapshot
    from src.domain.value_objects.trade_setup import TradeSetup

from src.application.ports.corporate_action_repository import CorporateActionRepository
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.stats import foreign_vwap_discount_pct
from src.application.use_case.assess_accumulation_evidence_use_case import (
    AssessAccumulationEvidenceRequest,
    AssessAccumulationEvidenceUseCase,
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
from src.domain.value_objects.accumulation_evidence import AccumulationEvidence
from src.domain.value_objects.idx_market import SHARES_PER_LOT

# Default setup targets (1:1 R:R, regime-unaware fallback)
_DEFAULT_TAKE_PROFIT = Decimal("5")
_DEFAULT_STOP_LOSS = Decimal("5")

# Regime-specific targets (validated direction: IHSG has documented regime cycles)
# MCE vocabulary (RISK_ON/NEUTRAL/VOLATILE/RISK_OFF).
_REGIME_TARGETS: dict[str, tuple[Decimal, Decimal]] = {
    "RISK_ON":  (Decimal("8"), Decimal("4")),   # 2:1 R:R — trending market
    "NEUTRAL":  (Decimal("5"), Decimal("5")),   # 1:1 R:R — range-bound
    "VOLATILE": (Decimal("3"), Decimal("3")),   # tight — minimize exposure
    "RISK_OFF": (Decimal("3"), Decimal("3")),   # capital preservation
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
    min_accum_score: float = 0.0  # filter: only include accumulation evidence >= this
    min_accum_score_enabled: bool = True
    min_signal_score: float = 0.0  # optional SignalEngine score filter
    min_signal_score_enabled: bool = False
    rsi_period: int = 14
    sma_period: int = 20
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
    # Phase E: risk profile for post-screening risk funnel (ignored when no risk_use_case)
    risk_profile: str = "balanced"

    def __init__(
        self,
        tickers: list[str],
        window_days: int = 7,
        min_net_buy_days: int = 2,
        min_accum_score: float = 0.0,
        min_accum_score_enabled: bool = True,
        min_signal_score: float = 0.0,
        min_signal_score_enabled: bool = False,
        rsi_period: int = 14,
        sma_period: int = 20,
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
        risk_profile: str = "balanced",
        min_score: float | None = None,
    ) -> None:
        # Deprecated compatibility for non-CLI application callers. The public CLI
        # uses --min-accum-score only; this keeps audit/backtest tests stable while
        # their call sites are migrated.
        if min_score is not None:
            min_accum_score = min_score
            min_accum_score_enabled = True
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
        self.sector_breadth_enabled = sector_breadth_enabled
        self.sector_breadth_threshold = sector_breadth_threshold
        self.sector_breadth_bonus_pts = sector_breadth_bonus_pts
        self.sector_breadth_min_tickers = sector_breadth_min_tickers
        self.tier1_broker_codes = tier1_broker_codes or TIER1_FOREIGN_BROKERS
        self.bci_cluster_min_count = bci_cluster_min_count
        self.bci_stable_min_count = bci_stable_min_count
        self.min_market_cap_idr = min_market_cap_idr
        self.min_piotroski = min_piotroski
        self.risk_profile = risk_profile


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
    accum_score: float  # 0–120 accumulation evidence score
    top_brokers: list[str] | None  # per-broker codes (Stockbit only)
    institutional_flag: bool  # True if major institutional broker present
    # Improvement #1: flow ratio signal
    avg_flow_ratio: float | None = None  # avg % of daily turnover that's foreign
    accumulation_evidence: AccumulationEvidence | None = None
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

    @property
    def score(self) -> float:
        """Deprecated alias for older application services; use accum_score."""
        return self.accum_score

    @score.setter
    def score(self, value: float) -> None:
        self.accum_score = value

    @property
    def score_breakdown(self) -> dict:
        """Deprecated alias for older display/tests; use accumulation_evidence."""
        if self.accumulation_evidence is None:
            return {}
        return self.accumulation_evidence.breakdown_dict

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
            "accum_score": self.accum_score,
            "top_brokers": self.top_brokers,
            "institutional_flag": self.institutional_flag,
            "bci_label": self.bci_label,
            "bci_tier1_count": self.bci_tier1_count,
            "vwap_pct": round(self.vwap_pct, 2) if self.vwap_pct is not None else None,
            "avg_flow_ratio": round(self.avg_flow_ratio, 2)
            if self.avg_flow_ratio is not None
            else None,
            "accumulation_evidence": (
                self.accumulation_evidence.to_dict()
                if self.accumulation_evidence is not None
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
            "latest_candle_date": self.latest_candle_date.isoformat() if self.latest_candle_date else None,
            "latest_broker_date": self.latest_broker_date.isoformat() if self.latest_broker_date else None,
            "forward_estimates": self.forward_estimates.to_dict() if self.forward_estimates else None,
            "signal_assessment": {
                "score": self.signal_assessment.assessment.score,
                "strength": self.signal_assessment.assessment.strength.value,
                "entry_quality": self.signal_assessment.assessment.entry_quality.value,
                "breakdown": self.signal_assessment.assessment.breakdown_dict,
                "coverage_warning": self.signal_assessment.coverage_warning,
            } if self.signal_assessment else None,
            "risk_status": self.risk_assessment.risk_level_name if self.risk_assessment else None,
            "risk_level": self.risk_assessment.risk_level_name if self.risk_assessment else None,
            "risk_confidence": self.risk_assessment.confidence if self.risk_assessment else None,
            "risk_gate": self.risk_assessment.gate_triggered if self.risk_assessment else None,
        }


@dataclass
class AccumulationScreenResponse:
    """Screener output."""

    candidates: list[AccumulationCandidate]  # sorted by score descending
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
    """Default screener ordering: verdict, signal, accumulation evidence, seasonality."""
    return (
        float(_trade_action_rank(candidate)),
        float(candidate.signal_assessment.assessment.score if candidate.signal_assessment else 0),
        candidate.accum_score,
        candidate.seasonal_edge.score if candidate.seasonal_edge else 0.0,
    )


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
        accumulation_evidence_use_case: AssessAccumulationEvidenceUseCase | None = None,
    ) -> None:
        from src.application.services.signal_engine import SignalEngine as _SignalEngine

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
        self._accumulation_evidence_uc = (
            accumulation_evidence_use_case or AssessAccumulationEvidenceUseCase()
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
        skipped = 0
        uses_stockbit = False

        for ticker in request.tickers:
            result = self._evaluate_ticker(
                ticker=ticker,
                window_days=request.window_days,
                today=today,
                min_net_buy_days=request.min_net_buy_days,
                rsi_period=request.rsi_period,
                sma_period=request.sma_period,
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
                if (
                    request.min_market_cap_idr > 0
                    and (
                        result.fundamentals is None
                        or result.fundamentals.market_cap_idr is None
                        or result.fundamentals.market_cap_idr < request.min_market_cap_idr
                    )
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

            evidence_resp = self._accumulation_evidence_uc.execute(
                AssessAccumulationEvidenceRequest(
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
            result.accumulation_evidence = evidence_resp.evidence
            result.accum_score = evidence_resp.evidence.accum_score

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
                )

            # Insider activity: director/commissioner transactions in last 90 days
            insider_txns: list = []
            insider_net_buy_ratio: float | None = None
            if self._insider_provider is not None:
                from datetime import timedelta
                from src.domain.value_objects.insider_transaction import compute_net_buy_ratio

                insider_lookback = 90
                insider_txns = self._insider_provider.get_insider_transactions(
                    ticker=result.ticker,
                    from_date=today - timedelta(days=insider_lookback),
                    to_date=today,
                    action_type="ALL",
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
                )

            # Forward EPS estimates — used in composite score
            if self._forward_estimates_provider is not None:
                result.forward_estimates = self._forward_estimates_provider.get_forward_estimates(
                    ticker=result.ticker,
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
            result.signal_assessment = self._signal_engine.evaluate_with_context(
                result.ticker, signal_ctx
            )

            if (
                request.min_accum_score_enabled
                and result.accum_score < request.min_accum_score
            ):
                continue
            if (
                request.min_signal_score_enabled
                and (
                    result.signal_assessment is None
                    or result.signal_assessment.assessment.score < request.min_signal_score
                )
            ):
                continue
            candidates.append(result)

        # Phase 3.2: sector breadth post-processing pass
        if request.sector_breadth_enabled and self._ticker_to_group:
            self._apply_sector_breadth(candidates, request)

        # Phase E (Rec 14): post-screening risk funnel — runs only on survivors,
        # not on all 800+ tickers. Reuses already-loaded fundamentals + bandar
        # data from candidates (Rec 15 data sharing — zero extra provider queries).
        if self._risk_use_case is not None:
            self._run_risk_funnel(candidates, today, request.risk_profile)

        candidates.sort(key=_screen_sort_key, reverse=True)

        return AccumulationScreenResponse(
            candidates=candidates,
            screened_at=today,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=skipped,
            provider="stockbit" if uses_stockbit else "idx",
        )

    def _run_risk_funnel(
        self,
        candidates: list[AccumulationCandidate],
        as_of_date: date,
        risk_profile: str,
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
                        candidate.fundamentals.piotroski_f_score
                        if candidate.fundamentals else None
                    ),
                    market_cap_idr=(
                        candidate.fundamentals.market_cap_idr
                        if candidate.fundamentals else None
                    ),
                    free_float_pct=(
                        candidate.shareholding.free_float_pct
                        if candidate.shareholding is not None else None
                    ),
                    five_day_accdist=(
                        candidate.bandar_detector.five_day_accdist
                        if candidate.bandar_detector else None
                    ),
                    bandar_is_distributing=(
                        candidate.bandar_detector.is_distributing
                        if candidate.bandar_detector else False
                    ),
                )
                resp = self._risk_use_case.execute(  # type: ignore[union-attr]
                    AssessRiskRequest(
                        ticker=candidate.ticker,
                        sensitivity=risk_profile,
                        gate_context=gate_ctx,
                    )
                )
                candidate.risk_assessment = resp.assessment
                if candidate.signal_assessment is not None:
                    try:
                        trade_resp = trade_setup_uc.execute(AssessTradeSetupRequest(
                            ticker=candidate.ticker,
                            snapshot_date=as_of_date,
                            signal_response=candidate.signal_assessment,
                            risk_response=resp,
                        ))
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
            bb_width, bb_width_pctile = self._compute_bb_squeeze(candles)

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
                window_20 = candles[-20:]
                total_vol = sum(c.volume for c in window_20)
                if total_vol > 0:
                    total_tpv = sum(
                        (c.high + c.low + c.close) / Decimal("3") * c.volume for c in window_20
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
            accum_score=0.0,  # set after by AssessAccumulationEvidenceUseCase
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
                    m.accum_score += request.sector_breadth_bonus_pts
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

        if pct_diff > 2.0:
            return "UP"
        elif pct_diff < -2.0:
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

    @staticmethod
    def _compute_resistance(
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
        if len(candles) >= 200:
            ma200 = Decimal(str(sum(c.close for c in candles[-200:]) / 200))

        week52_high: Decimal | None = None
        if len(candles) >= 1:
            week52_high = max(c.high for c in candles[-252:])

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
        w for w in windows
        if candidates_by_window.get(w) and candidates_by_window[w].accum_score >= coiled_spring_min_score
    ]

    for w in windows:
        c = candidates_by_window.get(w)
        if (c and c.accum_score >= coiled_spring_min_score
                and c.bb_width_pctile is not None
                and c.bb_width_pctile <= coiled_spring_bb_pctile):
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
