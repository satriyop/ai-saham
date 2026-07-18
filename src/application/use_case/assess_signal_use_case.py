"""
AssessSignalUseCase — archived six-factor baseline composite signal scoring.

Implements the archived 6-factor weighted scoring algorithm from AccumulationScreenUseCase.
It is used only for audit/parity diagnostics. It does not produce canonical SignalEngine
authority coverage. It must not be used for production decisions, observations, tuning,
or promotion.

Layer: Application
Depends on: domain only (SignalAssessment, SignalContext)
"""

from __future__ import annotations

from datetime import date

from src.application.dto.assess_signal import AssessSignalRequest, AssessSignalResponse
from src.application.services.company_quality_scoring import (
    score_analyst as _shared_score_analyst,
)
from src.application.services.company_quality_scoring import (
    score_forward_pe as _shared_score_forward_pe,
)
from src.application.services.company_quality_scoring import (
    score_insider_activity as _shared_score_insider_activity,
)
from src.application.services.company_quality_scoring import (
    score_seasonality as _shared_score_seasonality,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.services.stats import interpolate
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalContext,
    SignalStrength,
)

# Default weights — used when no YAML config is provided
_DEFAULT_WEIGHTS: dict[str, float] = {
    "bandar_intensity": 0.20,
    "foreign_flow_quality": 0.20,
    "insider_activity": 0.20,
    "seasonality_edge": 0.15,
    "analyst_consensus": 0.15,
    "forward_valuation": 0.10,
}


class AssessSignalUseCase:
    """
    Archived six-factor baseline scorer. Used only for audit/parity diagnostics.
    Does not produce canonical SignalEngine authority coverage. Must not be used
    for production decisions, observations, tuning, or promotion.

    Callers are responsible for populating SignalContext from enrichment
    providers before calling execute(). When signal_context is None, the
    use case creates an empty context (all factors neutral).
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
            # Archived six-factor scorer does not evaluate canonical production
            # evidence-group authority.
            signal_authority_coverage=None,
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
                f"{missing}/6 enrichment factors missing — archived baseline score defaulted to neutral "
                f"({self._config.missing_data.neutral_score:g}) "
                f"for those factors. Refresh or import enrichment data for more complete archived baseline diagnostics."
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
            f"Archived baseline score {score}/100 — {strength.value}, {entry_quality.value}"
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

# Compatibility surface:
# - Canonical import(s):
#   - signal config symbols (AlphaTriggerConfig, AlphaTriggerRouteFractionsConfig,
#     AnalystBearishFlagConfig, AnalystScoringConfig, BandarScoringConfig,
#     DecisionPolicyConfig, EvidenceGroupConfig, EvidenceGroupsConfig,
#     ForeignFlowScoreMappingConfig, ForwardPeScoringConfig,
#     InsiderSellingFlagConfig, NeutralRegimeConfig, RegimeConditioningConfig,
#     RegimeDecisionPolicyConfig, RiskOffRegimeConfig, SeasonalityScoringConfig,
#     SetupRegimeActionConfig, SignalClassificationConfig,
#     SignalEnrichmentConfig, SignalFlagsConfig, SignalInputMappingConfig,
#     SignalMissingDataConfig, SignalScoringConfig,
#     ValuationStretchedFlagConfig, VolatileRegimeConfig) ->
#     src.application.services.signal_engine_config
# - Allowed contents:
#   - re-export only for the config symbols above. This module remains
#     canonical for AssessSignalUseCase, _DEFAULT_WEIGHTS, and _interpolate,
#     which are not part of the compatibility surface.
# - Expiry:
#   - permanent public API, or remove after internal imports migrate to
#     src.application.services.signal_engine_config directly.
# Backward-compatible re-exports
__all__ = [
    "AssessSignalRequest",
    "AssessSignalResponse",
    "AssessSignalUseCase",
    "_DEFAULT_WEIGHTS",
    "_interpolate",
    "SignalClassificationConfig",
    "SignalMissingDataConfig",
    "ForeignFlowScoreMappingConfig",
    "SignalInputMappingConfig",
    "SignalEnrichmentConfig",
    "EvidenceGroupConfig",
    "EvidenceGroupsConfig",
    "ValuationStretchedFlagConfig",
    "AnalystBearishFlagConfig",
    "InsiderSellingFlagConfig",
    "SignalFlagsConfig",
    "NeutralRegimeConfig",
    "RiskOffRegimeConfig",
    "VolatileRegimeConfig",
    "RegimeConditioningConfig",
    "RegimeDecisionPolicyConfig",
    "SetupRegimeActionConfig",
    "DecisionPolicyConfig",
    "AlphaTriggerRouteFractionsConfig",
    "AlphaTriggerConfig",
    "SignalEngineConfig",
    "AnalystScoringConfig",
    "BandarScoringConfig",
    "ForwardPeScoringConfig",
    "SeasonalityScoringConfig",
    "SignalScoringConfig",
]

from src.application.services.signal_engine_config import (  # noqa: E402, F401
    AlphaTriggerConfig,
    AlphaTriggerRouteFractionsConfig,
    AnalystBearishFlagConfig,
    AnalystScoringConfig,
    BandarScoringConfig,
    DecisionPolicyConfig,
    EvidenceGroupConfig,
    EvidenceGroupsConfig,
    ForeignFlowScoreMappingConfig,
    ForwardPeScoringConfig,
    InsiderSellingFlagConfig,
    NeutralRegimeConfig,
    RegimeConditioningConfig,
    RegimeDecisionPolicyConfig,
    RiskOffRegimeConfig,
    SeasonalityScoringConfig,
    SetupRegimeActionConfig,
    SignalClassificationConfig,
    SignalEnrichmentConfig,
    SignalFlagsConfig,
    SignalInputMappingConfig,
    SignalMissingDataConfig,
    SignalScoringConfig,
    ValuationStretchedFlagConfig,
    VolatileRegimeConfig,
)
