"""
AssessSignalUseCase — composite signal scoring for a single ticker.

Implements the 6-factor weighted scoring algorithm previously embedded as
_composite_score() in AccumulationScreenUseCase (lines ~358–468). Extracted
here so SignalEngine can call it independently without the screener context.

Scoring is deterministic given a SignalContext. No IO, no providers, no
side effects. All defaults (missing data → neutral 50.0) are explicit.

Layer: Application
Depends on: domain only (SignalAssessment, SignalContext)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.application.services.company_quality_scoring import (
    score_analyst as _shared_score_analyst,
    score_forward_pe as _shared_score_forward_pe,
    score_insider_activity as _shared_score_insider_activity,
    score_seasonality as _shared_score_seasonality,
)
from src.application.services.signal_scoring_config import (
    AnalystScoringConfig,
    BandarScoringConfig,
    ForwardPeScoringConfig,
    SeasonalityScoringConfig,
    SignalScoringConfig,
)
from src.application.services.stats import interpolate
from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
    EvidenceRegistration,
)
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalContext,
    SignalStrength,
)

@dataclass(frozen=True)
class SignalClassificationConfig:
    strong_min_score: int = 70
    moderate_min_score: int = 45
    enter_min_confidence: float = 0.70
    watch_min_confidence: float = 0.40


@dataclass(frozen=True)
class SignalMissingDataConfig:
    neutral_score: float = 50.0
    coverage_warning_missing_factors: int = 3


# SeasonalityScoringConfig, AnalystScoringConfig, ForwardPeScoringConfig,
# BandarScoringConfig, and SignalScoringConfig now live in
# src/application/services/signal_scoring_config.py and are imported above.
# They remain re-exported from this module for backward-compatible imports.


@dataclass(frozen=True)
class ForeignFlowScoreMappingConfig:
    max_score: float = 100.0
    clamp: bool = True


@dataclass(frozen=True)
class SignalInputMappingConfig:
    foreign_flow_score: ForeignFlowScoreMappingConfig = field(
        default_factory=ForeignFlowScoreMappingConfig
    )


@dataclass(frozen=True)
class SignalEnrichmentConfig:
    insider_lookback_days: int = 90


# ── Phase 4: evidence-group and flag config ───────────────────────────────────

@dataclass(frozen=True)
class EvidenceGroupConfig:
    weight: float = 1.0


@dataclass(frozen=True)
class EvidenceGroupsConfig:
    setup_quality: EvidenceGroupConfig = field(
        default_factory=lambda: EvidenceGroupConfig(weight=0.60)
    )
    flow_confirmation: EvidenceGroupConfig = field(
        default_factory=lambda: EvidenceGroupConfig(weight=0.40)
    )


@dataclass(frozen=True)
class ValuationStretchedFlagConfig:
    enabled: bool = True
    forward_pe_threshold: float = 50.0
    score_penalty: int = 10


@dataclass(frozen=True)
class AnalystBearishFlagConfig:
    enabled: bool = True
    buy_ratio_threshold: float = 0.20
    score_penalty: int = 8


@dataclass(frozen=True)
class InsiderSellingFlagConfig:
    enabled: bool = True
    net_buy_ratio_threshold: float = -0.30
    score_penalty: int = 12


@dataclass(frozen=True)
class SignalFlagsConfig:
    valuation_stretched: ValuationStretchedFlagConfig = field(
        default_factory=ValuationStretchedFlagConfig
    )
    analyst_bearish: AnalystBearishFlagConfig = field(
        default_factory=AnalystBearishFlagConfig
    )
    insider_selling: InsiderSellingFlagConfig = field(
        default_factory=InsiderSellingFlagConfig
    )


# ── Phase 5: regime-conditional group score conditioning ──────────────────────

@dataclass(frozen=True)
class NeutralRegimeConfig:
    """NEUTRAL regime: discount weak flow confirmation below threshold."""
    weak_flow_threshold: float = 50.0
    weak_flow_discount: float = 0.80


@dataclass(frozen=True)
class RiskOffRegimeConfig:
    """RISK_OFF regime: discount weak (non-MATCH) setup evidence."""
    weak_setup_threshold: float = 60.0   # below this = PARTIAL or NO_MATCH
    weak_setup_discount: float = 0.50


@dataclass(frozen=True)
class VolatileRegimeConfig:
    """VOLATILE regime: discount both evidence groups."""
    setup_discount: float = 0.70
    flow_discount: float = 0.80


@dataclass(frozen=True)
class RegimeConditioningConfig:
    """Per-regime group score conditioning applied before renormalization.

    RISK_ON: no conditioning (normal confidence).
    NEUTRAL: weak flow discounted (market needs stronger flow confirmation).
    RISK_OFF: weak setup discounted (only MATCH-quality setups count).
    VOLATILE: both groups discounted (higher bar in fast-moving markets).
    """
    neutral: NeutralRegimeConfig = field(default_factory=NeutralRegimeConfig)
    risk_off: RiskOffRegimeConfig = field(default_factory=RiskOffRegimeConfig)
    volatile: VolatileRegimeConfig = field(default_factory=VolatileRegimeConfig)


@dataclass(frozen=True)
class RegimeDecisionPolicyConfig:
    enter_allowed: bool = True
    max_decision: str = "ENTER"
    regime_size_multiplier: float = 1.0
    enter_threshold: int | None = None
    watch_threshold: int = 45
    min_coverage: float = 0.0
    min_conviction: float = 0.0


@dataclass(frozen=True)
class SetupRegimeActionConfig:
    max_decision: str = "ENTER"


@dataclass(frozen=True)
class DecisionPolicyConfig:
    regime_policy: dict[str, RegimeDecisionPolicyConfig] = field(
        default_factory=lambda: {
            "RISK_ON": RegimeDecisionPolicyConfig(
                enter_allowed=True,
                max_decision="ENTER",
                regime_size_multiplier=1.0,
                enter_threshold=70,
                watch_threshold=45,
                min_coverage=0.0,
                min_conviction=0.0,
            ),
            "NEUTRAL": RegimeDecisionPolicyConfig(
                enter_allowed=True,
                max_decision="ENTER",
                regime_size_multiplier=0.50,
                enter_threshold=72,
                watch_threshold=45,
                min_coverage=0.0,
                min_conviction=0.0,
            ),
            "RISK_OFF": RegimeDecisionPolicyConfig(
                enter_allowed=False,
                max_decision="WATCH",
                regime_size_multiplier=0.25,
                enter_threshold=None,
                watch_threshold=60,
                min_coverage=0.80,
                min_conviction=0.78,
            ),
            "VOLATILE": RegimeDecisionPolicyConfig(
                enter_allowed=False,
                max_decision="WATCH",
                regime_size_multiplier=0.0,
                enter_threshold=None,
                watch_threshold=65,
                min_coverage=1.0,
                min_conviction=1.0,
            ),
        }
    )
    setup_regime_policy: dict[str, dict[str, str]] = field(default_factory=dict)
    setup_regime_actions: dict[str, SetupRegimeActionConfig] = field(
        default_factory=lambda: {
            "allowed": SetupRegimeActionConfig(max_decision="ENTER"),
            "restricted_or_watch_only": SetupRegimeActionConfig(max_decision="WATCH"),
            "enter_disabled": SetupRegimeActionConfig(max_decision="WATCH"),
            "allowed_if_flow_confirmation_strong": SetupRegimeActionConfig(
                max_decision="ENTER"
            ),
        }
    )
    # A2: caps applied when regime quality metadata is available
    regime_confidence_min_enter: float = 0.35   # cap ENTER→WATCH when confidence < this
    regime_transitioning_cap_enter: bool = True  # cap ENTER→WATCH when stability == TRANSITIONING


@dataclass(frozen=True)
class AlphaTriggerRouteFractionsConfig:
    """Per-horizon group routing fractions. Trigger fraction is always derived."""

    by_horizon: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "TACTICAL_3D": {
                "setup_quality": 0.00,
                "institutional_flow": 0.70,
                "market_context": 0.25,
                "company_quality_context": 1.00,
            },
            "SWING_10D": {
                "setup_quality": 0.00,
                "institutional_flow": 0.80,
                "market_context": 0.60,
                "company_quality_context": 1.00,
            },
            "ACCUM_20D": {
                "setup_quality": 0.10,
                "institutional_flow": 0.90,
                "market_context": 0.75,
                "company_quality_context": 1.00,
            },
        }
    )


@dataclass(frozen=True)
class AlphaTriggerConfig:
    enabled: bool = True
    default_horizon: str = "SWING_10D"
    group_weights: dict[str, float] = field(
        default_factory=lambda: {
            "setup_quality": 0.35,
            "institutional_flow": 0.30,
            "market_context": 0.25,
            "company_quality_context": 0.10,
        }
    )
    route_fractions: dict[str, dict[str, float]] = field(
        default_factory=lambda: AlphaTriggerRouteFractionsConfig().by_horizon
    )
    horizon_alpha_weights: dict[str, float] = field(
        default_factory=lambda: {
            "TACTICAL_3D": 0.20,
            "SWING_10D": 0.40,
            "ACCUM_20D": 0.50,
        }
    )
    low_weight_cap: float = 0.10
    evidence_registrations: dict[str, EvidenceRegistration] = field(
        default_factory=lambda: {
            "setup_quality": EvidenceRegistration(
                evidence_name="setup_quality",
                status=EvidenceAuthorityStatus.PRODUCTION,
            ),
            "institutional_flow": EvidenceRegistration(
                evidence_name="institutional_flow",
                status=EvidenceAuthorityStatus.PRODUCTION,
            ),
            "market_context": EvidenceRegistration(
                evidence_name="market_context",
                status=EvidenceAuthorityStatus.DIAGNOSTIC,
            ),
            "company_quality_context": EvidenceRegistration(
                evidence_name="company_quality_context",
                status=EvidenceAuthorityStatus.DIAGNOSTIC,
            ),
        }
    )


@dataclass(frozen=True)
class SignalEngineConfig:
    classification: SignalClassificationConfig = field(default_factory=SignalClassificationConfig)
    missing_data: SignalMissingDataConfig = field(default_factory=SignalMissingDataConfig)
    scoring: SignalScoringConfig = field(default_factory=SignalScoringConfig)
    input_mapping: SignalInputMappingConfig = field(default_factory=SignalInputMappingConfig)
    enrichment: SignalEnrichmentConfig = field(default_factory=SignalEnrichmentConfig)
    evidence_groups: EvidenceGroupsConfig = field(default_factory=EvidenceGroupsConfig)
    flags: SignalFlagsConfig = field(default_factory=SignalFlagsConfig)
    regime_conditioning: RegimeConditioningConfig = field(default_factory=RegimeConditioningConfig)
    decision_policy: DecisionPolicyConfig = field(default_factory=DecisionPolicyConfig)
    alpha_trigger: AlphaTriggerConfig = field(default_factory=AlphaTriggerConfig)

# Default weights — used when no YAML config is provided (identical to historical hardcoded values)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "bandar_intensity": 0.20,
    "foreign_flow_quality": 0.20,
    "insider_activity": 0.20,
    "seasonality_edge": 0.15,
    "analyst_consensus": 0.15,
    "forward_valuation": 0.10,
}


@dataclass
class AssessSignalRequest:
    ticker: str
    signal_context: SignalContext | None = None


@dataclass
class AssessSignalResponse:
    ticker: str
    assessment: SignalAssessment
    coverage_warning: str | None = None
    signal_score_raw: int | None = None  # pre-regime score; None means no regime adjustment applied
    # Phase 4 evidence fields — None/empty when produced by the old flat path
    evidence_confidence: float | None = None   # legacy alias for coverage_score (0.0–1.0; None = flat-path)
    active_flags: tuple[str, ...] = field(default_factory=tuple)
    flag_adjustment: int = 0
    raw_group_score: int | None = None          # score before flag adjustments
    raw_exact_score: float | None = None
    alpha_trigger_score: AlphaTriggerScore | None = None

    @property
    def coverage_score(self) -> float | None:
        """Canonical name: evidence completeness (0.0–1.0). Alias for evidence_confidence."""
        return self.evidence_confidence

    @property
    def score(self) -> int:
        return self.assessment.score

    @property
    def strength(self) -> str:
        return self.assessment.strength.value

    @property
    def entry_quality(self) -> str:
        return self.assessment.entry_quality.value


class AssessSignalUseCase:
    """
    Pure computation: no repository, no providers, no state.

    Callers are responsible for populating SignalContext from enrichment
    providers before calling execute(). When signal_context is None, the
    use case creates an empty context (all factors neutral).

    weights: renormalized factor weights loaded from config/signal_engine.yaml by the
    factory. When None, _DEFAULT_WEIGHTS are used (preserves historical behavior).
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        config: SignalEngineConfig | None = None,
    ) -> None:
        self._weights = weights or _DEFAULT_WEIGHTS.copy()
        self._config = config or SignalEngineConfig()

    def execute(self, request: AssessSignalRequest) -> AssessSignalResponse:
        ctx = request.signal_context or SignalContext(
            ticker=request.ticker, snapshot_date=date.today()
        )
        assessment = self._compute(ctx)
        warning = self._coverage_warning(ctx)
        return AssessSignalResponse(
            ticker=request.ticker,
            assessment=assessment,
            coverage_warning=warning,
        )

    # ── scoring ──────────────────────────────────────────────────────────────

    def _compute(self, ctx: SignalContext) -> SignalAssessment:
        bandar, bandar_has = self._score_bandar(ctx)
        foreign, foreign_has = self._score_foreign(ctx)
        insider, insider_has = self._score_insider_activity(ctx)
        seasonality, seasonality_has = self._score_seasonality(ctx)
        analyst, analyst_has = self._score_analyst(ctx)
        fwd, fwd_has = self._score_forward_pe(ctx)

        w = self._weights
        total = (
            bandar * w.get("bandar_intensity", 0)
            + foreign * w.get("foreign_flow_quality", 0)
            + insider * w.get("insider_activity", 0)
            + seasonality * w.get("seasonality_edge", 0)
            + analyst * w.get("analyst_consensus", 0)
            + fwd * w.get("forward_valuation", 0)
        )
        score = max(0, min(100, round(total)))

        strength = self._classify_strength(score)
        entry_quality = self._classify_entry(strength)

        breakdown = (
            ("bandar_intensity", round(bandar, 2)),
            ("foreign_flow_quality", round(foreign, 2)),
            ("insider_activity", round(insider, 2)),
            ("seasonality_edge", round(seasonality, 2)),
            ("analyst_consensus", round(analyst, 2)),
            ("forward_valuation", round(fwd, 2)),
        )

        rationale = self._build_rationale(
            ctx, score, strength, entry_quality,
            breakdown,
            has_flags=(bandar_has, foreign_has, insider_has, seasonality_has, analyst_has, fwd_has),
        )

        return SignalAssessment(
            ticker=ctx.ticker,
            score=score,
            strength=strength,
            entry_quality=entry_quality,
            breakdown=breakdown,
            rationale=rationale,
            snapshot_date=ctx.snapshot_date,
            confidence_score=1.0,
        )

    # ── factor scorers ───────────────────────────────────────────────────────

    def _score_bandar(self, ctx: SignalContext) -> tuple[float, bool]:
        """
        Map broad_score from its dynamic range to 0–100.

        Range = (3 + num_optional) * 2 where num_optional is the count of
        top3/top5/top10 accdist signals that were populated (0–3).
        Default max_range = 6 (only today + five_day + top1 present).
        """
        if ctx.bandar_broad_score is None:
            return self._config.missing_data.neutral_score, False
        max_r = ctx.bandar_max_range
        if max_r <= 0:
            return self._config.missing_data.neutral_score, False
        normalized = (ctx.bandar_broad_score + max_r) / (2 * max_r) * 100.0
        return max(0.0, min(100.0, normalized)), True

    def _score_foreign(self, ctx: SignalContext) -> tuple[float, bool]:
        """Foreign flow quality (0.0–1.0 pre-normalized) → 0–100."""
        if ctx.foreign_flow_quality is None:
            return self._config.missing_data.neutral_score, False
        return max(0.0, min(100.0, ctx.foreign_flow_quality * 100.0)), True

    def _score_insider_activity(self, ctx: SignalContext) -> tuple[float, bool]:
        """Insider net buy direction → 0–100. Delegates to shared scorer."""
        return _shared_score_insider_activity(
            ctx, neutral_score=self._config.missing_data.neutral_score
        )

    def _score_seasonality(self, ctx: SignalContext) -> tuple[float, bool]:
        """Directional seasonal edge → 0–100. Delegates to shared scorer."""
        cfg = self._config.scoring.seasonality
        return _shared_score_seasonality(
            ctx,
            tailwind_min_avg_return_pct=cfg.tailwind_min_avg_return_pct,
            tailwind_min_win_rate_pct=cfg.tailwind_min_win_rate_pct,
            headwind_max_avg_return_pct=cfg.headwind_max_avg_return_pct,
            headwind_max_win_rate_pct=cfg.headwind_max_win_rate_pct,
            neutral_score=self._config.missing_data.neutral_score,
        )

    def _score_analyst(self, ctx: SignalContext) -> tuple[float, bool]:
        """Analyst consensus conviction → 0–100. Delegates to shared scorer."""
        cfg = self._config.scoring.analyst
        return _shared_score_analyst(
            ctx,
            buy_score_max_points=cfg.buy_score_max_points,
            upside_score_max_points=cfg.upside_score_max_points,
            upside_cap_pct=cfg.upside_cap_pct,
            neutral_score=self._config.missing_data.neutral_score,
        )

    def _score_forward_pe(self, ctx: SignalContext) -> tuple[float, bool]:
        """Forward-P/E valuation attractiveness → 0–100. Delegates to shared scorer."""
        cfg = self._config.scoring.forward_pe
        return _shared_score_forward_pe(
            ctx,
            very_cheap_pe=cfg.very_cheap_pe,
            cheap_pe=cfg.cheap_pe,
            fair_pe=cfg.fair_pe,
            expensive_pe=cfg.expensive_pe,
            very_cheap_score=cfg.very_cheap_score,
            cheap_score=cfg.cheap_score,
            fair_score=cfg.fair_score,
            expensive_score=cfg.expensive_score,
            post_expensive_pe_step=cfg.post_expensive_pe_step,
            post_expensive_score_decay=cfg.post_expensive_score_decay,
            neutral_score=self._config.missing_data.neutral_score,
        )

    # ── classification ───────────────────────────────────────────────────────

    def _classify_strength(self, score: int) -> SignalStrength:
        cfg = self._config.classification
        if score >= cfg.strong_min_score:
            return SignalStrength.STRONG
        if score >= cfg.moderate_min_score:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    @staticmethod
    def _classify_entry(strength: SignalStrength) -> EntryQuality:
        if strength == SignalStrength.STRONG:
            return EntryQuality.ENTER
        if strength == SignalStrength.MODERATE:
            return EntryQuality.WATCH
        return EntryQuality.AVOID

    # ── coverage ─────────────────────────────────────────────────────────────

    def _coverage_warning(self, ctx: SignalContext) -> str | None:
        missing = sum([
            ctx.bandar_broad_score is None,
            ctx.foreign_flow_quality is None,
            ctx.insider_net_buy_ratio is None,
            ctx.seasonality_win_rate is None,
            ctx.analyst_buy_pct is None,
            ctx.forward_pe is None,
        ])
        if missing >= self._config.missing_data.coverage_warning_missing_factors:
            return (
                f"{missing}/6 enrichment factors missing — score defaulted to neutral "
                f"({self._config.missing_data.neutral_score:g}) "
                f"for those factors. Refresh or import enrichment data for more accurate scores."
            )
        return None

    # ── rationale ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_rationale(
        ctx: SignalContext,
        score: int,
        strength: SignalStrength,
        entry_quality: EntryQuality,
        breakdown: tuple[tuple[str, float], ...],
        has_flags: tuple[bool, ...],
    ) -> tuple[str, ...]:
        labels = {
            "bandar_intensity": "Bandar accumulation",
            "foreign_flow_quality": "Foreign flow",
            "insider_activity": "Insider activity",
            "seasonality_edge": "Seasonal edge",
            "analyst_consensus": "Analyst consensus",
            "forward_valuation": "Forward valuation",
        }
        has_map = dict(zip(
            ["bandar_intensity", "foreign_flow_quality", "insider_activity",
             "seasonality_edge", "analyst_consensus", "forward_valuation"],
            has_flags,
        ))

        lines = []
        # Sort factors by component score descending (most impactful first)
        for name, component in sorted(breakdown, key=lambda x: x[1], reverse=True):
            label = labels.get(name, name)
            if has_map.get(name):
                lines.append(f"{label}: {component:.0f}/100")
            else:
                lines.append(f"{label}: no data (neutral 50)")

        lines.append(
            f"Signal score {score}/100 — {strength.value}, {entry_quality.value}"
        )
        return tuple(lines)


def _interpolate(
    value: float,
    low_value: float,
    high_value: float,
    low_score: float,
    high_score: float,
) -> float:
    return interpolate(value, low_value, high_value, low_score, high_score)
