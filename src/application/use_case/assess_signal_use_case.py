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


@dataclass(frozen=True)
class SeasonalityScoringConfig:
    tailwind_min_avg_return_pct: float = 0.0
    tailwind_min_win_rate_pct: float = 50.0
    headwind_max_avg_return_pct: float = 0.0
    headwind_max_win_rate_pct: float = 50.0


@dataclass(frozen=True)
class AnalystScoringConfig:
    buy_score_max_points: float = 60.0
    upside_score_max_points: float = 40.0
    upside_cap_pct: float = 30.0


@dataclass(frozen=True)
class ForwardPeScoringConfig:
    very_cheap_pe: float = 10.0
    cheap_pe: float = 15.0
    fair_pe: float = 20.0
    expensive_pe: float = 30.0
    very_cheap_score: float = 95.0
    cheap_score: float = 75.0
    fair_score: float = 50.0
    expensive_score: float = 25.0
    post_expensive_pe_step: float = 10.0
    post_expensive_score_decay: float = 15.0


@dataclass(frozen=True)
class BandarScoringConfig:
    mandatory_signal_count: int = 3
    signal_score_unit: int = 2
    default_max_range: int = 6


@dataclass(frozen=True)
class SignalScoringConfig:
    bandar: BandarScoringConfig = field(default_factory=BandarScoringConfig)
    seasonality: SeasonalityScoringConfig = field(default_factory=SeasonalityScoringConfig)
    analyst: AnalystScoringConfig = field(default_factory=AnalystScoringConfig)
    forward_pe: ForwardPeScoringConfig = field(default_factory=ForwardPeScoringConfig)


@dataclass(frozen=True)
class ForeignFlowScoreMappingConfig:
    max_score: float = 120.0
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
    evidence_confidence: float | None = None   # 0.0–1.0; None = flat-path, no evidence tracking
    active_flags: tuple[str, ...] = field(default_factory=tuple)
    flag_adjustment: int = 0
    raw_group_score: int | None = None          # score before flag adjustments
    raw_exact_score: float | None = None
    alpha_trigger_score: AlphaTriggerScore | None = None

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
        """
        Insider net buy ratio (-1.0 to +1.0) → 0–100.

        -1.0 (full selling) → 0, 0.0 (neutral) → 50, +1.0 (full buying) → 100.
        Returns neutral 50.0 when no insider data is available (no provider yet).
        """
        if ctx.insider_net_buy_ratio is None:
            return self._config.missing_data.neutral_score, False
        return max(0.0, min(100.0, (ctx.insider_net_buy_ratio + 1.0) / 2.0 * 100.0)), True

    def _score_seasonality(self, ctx: SignalContext) -> tuple[float, bool]:
        """
        Map seasonal win rate to 0–100 with direction awareness.

        Tailwind  (avg_return > 0 AND win_rate > 50): score = win_rate_pct
        Headwind  (avg_return < 0 AND win_rate < 50): score = win_rate_pct
        Neutral   (everything else):                   score = 50

        This is directional for long-candidate attractiveness: a historically
        weak month should reduce the score, not become a strong positive signal.
        """
        if ctx.seasonality_win_rate is None or ctx.seasonality_avg_return_pct is None:
            return self._config.missing_data.neutral_score, False
        if (
            ctx.seasonality_total_years is None
            or ctx.seasonality_total_years < 5
        ):
            return self._config.missing_data.neutral_score, False

        win = ctx.seasonality_win_rate
        avg = ctx.seasonality_avg_return_pct
        cfg = self._config.scoring.seasonality
        is_tailwind = (
            avg > cfg.tailwind_min_avg_return_pct
            and win > cfg.tailwind_min_win_rate_pct
        )
        is_headwind = (
            avg < cfg.headwind_max_avg_return_pct
            and win < cfg.headwind_max_win_rate_pct
        )

        if is_tailwind:
            return win, True
        if is_headwind:
            return win, True
        return self._config.missing_data.neutral_score, True

    def _score_analyst(self, ctx: SignalContext) -> tuple[float, bool]:
        """
        Analyst consensus: buy% (max 60 pts) + upside capped at 30% (max 40 pts).

        analyst_buy_pct:  0.0–1.0  fraction of buy recommendations
        analyst_upside_pct: percentage, e.g. 15.0 = 15% price target upside
        """
        if ctx.analyst_buy_pct is None:
            return self._config.missing_data.neutral_score, False
        cfg = self._config.scoring.analyst
        buy_score = ctx.analyst_buy_pct * cfg.buy_score_max_points
        upside_score = (
            max(0.0, min(cfg.upside_cap_pct, ctx.analyst_upside_pct or 0.0))
            / cfg.upside_cap_pct
            * cfg.upside_score_max_points
            if cfg.upside_cap_pct > 0
            else 0.0
        )
        return min(100.0, buy_score + upside_score), True

    def _score_forward_pe(self, ctx: SignalContext) -> tuple[float, bool]:
        """
        Forward P/E → 0–100 via smooth linear interpolation across price tiers.

        P/E ≤ 0 (loss-maker / unavailable) → neutral 50
        P/E ≤ 10                            → 95  (very cheap)
        P/E ≤ 15                            → 95→75 linear
        P/E ≤ 20                            → 75→50 linear
        P/E ≤ 30                            → 50→25 linear
        P/E > 30                            → approaches 0

        Ported from _composite_score() in accumulation_screen_use_case.py.
        """
        pe = ctx.forward_pe
        if pe is None or pe <= 0:
            return self._config.missing_data.neutral_score, False

        cfg = self._config.scoring.forward_pe
        if pe <= cfg.very_cheap_pe:
            fwd = cfg.very_cheap_score
        elif pe <= cfg.cheap_pe:
            fwd = _interpolate(
                pe, cfg.very_cheap_pe, cfg.cheap_pe,
                cfg.very_cheap_score, cfg.cheap_score,
            )
        elif pe <= cfg.fair_pe:
            fwd = _interpolate(
                pe, cfg.cheap_pe, cfg.fair_pe,
                cfg.cheap_score, cfg.fair_score,
            )
        elif pe <= cfg.expensive_pe:
            fwd = _interpolate(
                pe, cfg.fair_pe, cfg.expensive_pe,
                cfg.fair_score, cfg.expensive_score,
            )
        else:
            decay = (
                (pe - cfg.expensive_pe)
                / cfg.post_expensive_pe_step
                * cfg.post_expensive_score_decay
                if cfg.post_expensive_pe_step > 0
                else cfg.expensive_score
            )
            fwd = max(0.0, cfg.expensive_score - decay)

        return fwd, True

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
