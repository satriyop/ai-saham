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

from dataclasses import dataclass
from datetime import date

from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalContext,
    SignalStrength,
)

_NEUTRAL = 50.0

# Classification thresholds (score-based; future: configurable per profile in YAML)
_STRONG_THRESHOLD = 70
_MODERATE_THRESHOLD = 45

# Minimum data coverage below which a warning is issued
_COVERAGE_WARNING_THRESHOLD = 3  # out of 6 factors

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
    profile: str = "balanced"
    signal_context: SignalContext | None = None


@dataclass
class AssessSignalResponse:
    ticker: str
    assessment: SignalAssessment
    profile: str
    coverage_warning: str | None = None
    signal_score_raw: int | None = None  # pre-regime score; None means no regime adjustment applied

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

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or _DEFAULT_WEIGHTS.copy()

    def execute(self, request: AssessSignalRequest) -> AssessSignalResponse:
        ctx = request.signal_context or SignalContext(
            ticker=request.ticker, snapshot_date=date.today()
        )
        assessment = self._compute(ctx)
        warning = self._coverage_warning(ctx)
        return AssessSignalResponse(
            ticker=request.ticker,
            assessment=assessment,
            profile=request.profile,
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
            return _NEUTRAL, False
        max_r = ctx.bandar_max_range
        normalized = (ctx.bandar_broad_score + max_r) / (2 * max_r) * 100.0
        return max(0.0, min(100.0, normalized)), True

    def _score_foreign(self, ctx: SignalContext) -> tuple[float, bool]:
        """Foreign flow quality (0.0–1.0 pre-normalized) → 0–100."""
        if ctx.foreign_flow_quality is None:
            return _NEUTRAL, False
        return max(0.0, min(100.0, ctx.foreign_flow_quality * 100.0)), True

    def _score_insider_activity(self, ctx: SignalContext) -> tuple[float, bool]:
        """
        Insider net buy ratio (-1.0 to +1.0) → 0–100.

        -1.0 (full selling) → 0, 0.0 (neutral) → 50, +1.0 (full buying) → 100.
        Returns neutral 50.0 when no insider data is available (no provider yet).
        """
        if ctx.insider_net_buy_ratio is None:
            return _NEUTRAL, False
        return max(0.0, min(100.0, (ctx.insider_net_buy_ratio + 1.0) / 2.0 * 100.0)), True

    def _score_seasonality(self, ctx: SignalContext) -> tuple[float, bool]:
        """
        Map seasonal win rate to 0–100 with direction awareness.

        Tailwind  (avg_return > 0 AND win_rate > 50): score = win_rate_pct
        Headwind  (avg_return < 0 AND win_rate < 50): score = 100 − win_rate_pct
        Neutral   (everything else):                   score = 50

        Note: this measures PATTERN STRENGTH, not directional fitness —
        a strong headwind (win_rate=20%) scores 80, same as a strong tailwind
        (win_rate=80%). Ported faithfully from _composite_score() in
        accumulation_screen_use_case.py; directional correction is R2 scope.
        """
        if ctx.seasonality_win_rate is None or ctx.seasonality_avg_return_pct is None:
            return _NEUTRAL, False

        win = ctx.seasonality_win_rate
        avg = ctx.seasonality_avg_return_pct
        is_tailwind = avg > 0 and win > 50.0
        is_headwind = avg < 0 and win < 50.0

        if is_tailwind:
            return win, True
        if is_headwind:
            return 100.0 - win, True
        return _NEUTRAL, True

    def _score_analyst(self, ctx: SignalContext) -> tuple[float, bool]:
        """
        Analyst consensus: buy% (max 60 pts) + upside capped at 30% (max 40 pts).

        analyst_buy_pct:  0.0–1.0  fraction of buy recommendations
        analyst_upside_pct: percentage, e.g. 15.0 = 15% price target upside
        """
        if ctx.analyst_buy_pct is None:
            return _NEUTRAL, False
        buy_score = ctx.analyst_buy_pct * 60.0
        upside_score = max(0.0, min(30.0, ctx.analyst_upside_pct or 0.0)) / 30.0 * 40.0
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
            return _NEUTRAL, False

        if pe <= 10:
            fwd = 95.0
        elif pe <= 15:
            fwd = 95.0 - (pe - 10.0) / 5.0 * 20.0
        elif pe <= 20:
            fwd = 75.0 - (pe - 15.0) / 5.0 * 25.0
        elif pe <= 30:
            fwd = 50.0 - (pe - 20.0) / 10.0 * 25.0
        else:
            fwd = max(0.0, 25.0 - (pe - 30.0) / 10.0 * 15.0)

        return fwd, True

    # ── classification ───────────────────────────────────────────────────────

    @staticmethod
    def _classify_strength(score: int) -> SignalStrength:
        if score >= _STRONG_THRESHOLD:
            return SignalStrength.STRONG
        if score >= _MODERATE_THRESHOLD:
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

    @staticmethod
    def _coverage_warning(ctx: SignalContext) -> str | None:
        missing = sum([
            ctx.bandar_broad_score is None,
            ctx.foreign_flow_quality is None,
            ctx.insider_net_buy_ratio is None,
            ctx.seasonality_win_rate is None,
            ctx.analyst_buy_pct is None,
            ctx.forward_pe is None,
        ])
        if missing >= _COVERAGE_WARNING_THRESHOLD:
            return (
                f"{missing}/6 enrichment factors missing — score defaulted to neutral (50) "
                f"for those factors. Run with --with-enrichment for accurate scores."
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
