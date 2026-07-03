"""
SetupEvidenceBuilder — application service.

Translates an existing SetupEvaluation and AccumulationCandidate into a
diagnostic SetupEvidence value object. Introduced in Phase 2 of the
SignalEngine refactor.

This service owns NO setup policy: it does not re-evaluate gates or thresholds.
The authoritative setup policy lives in EvaluateSwingSetupUseCase and
config/swing_setups.yaml. This builder only reshapes already-computed results
and applies freshness gating for the RS and volume sub-signals.

Layer: Application
Depends on: domain VOs (SetupEvidence, Freshness) + stdlib only.
No provider/repository/CLI imports.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.domain.value_objects.factor_evidence import Freshness
from src.domain.value_objects.setup_evidence import SetupEvidence

# IHSG benchmark candle history only becomes reliable from this date. Before it,
# a 5-day relative-strength window cannot be trusted, so RS is emitted as MISSING.
_IHSG_AVAILABLE_FROM = date(2025, 7, 1)

_MATCH_STRENGTH: dict[str, float] = {
    "MATCH": 100.0,
    "PARTIAL": 60.0,
    "NO_MATCH": 20.0,
}


class SetupEvidenceBuilder:
    """Builds diagnostic SetupEvidence from prior setup/accumulation results."""

    def build(
        self,
        candidate: Any,  # AccumulationCandidate; Any avoids domain coupling
        setup_eval: Any,  # SetupEvaluation; Any avoids domain coupling
        *,
        rs_vs_ihsg_5d: float | None = None,
        volume_trend_ratio: float | None = None,
        candle_source: str | None = None,
        analysis_date: date | None = None,
    ) -> SetupEvidence:
        # --- Setup gate result -------------------------------------------------
        match_value = getattr(getattr(setup_eval, "match", None), "value", "NO_MATCH")
        match_strength = _MATCH_STRENGTH.get(match_value, 20.0)
        # Renormalize match_value to a valid enum string (unknown -> NO_MATCH).
        if match_value not in _MATCH_STRENGTH:
            match_value = "NO_MATCH"
        setup_name = getattr(setup_eval, "name", None) if setup_eval is not None else None
        failed_gates = tuple(
            getattr(setup_eval, "failed_reasons", ()) if setup_eval is not None else ()
        )

        # --- Technical structure ----------------------------------------------
        trend = getattr(candidate, "trend", None) if candidate is not None else None
        rsi = getattr(candidate, "rsi", None) if candidate is not None else None
        bb_width_pctile = (
            getattr(candidate, "bb_width_pctile", None) if candidate is not None else None
        )
        vwap_discount_pct = (
            getattr(candidate, "vwap_discount_pct", None) if candidate is not None else None
        )
        vwap_pct = getattr(candidate, "vwap_pct", None) if candidate is not None else None

        # --- RS vs IHSG sub-signal (date-gated) -------------------------------
        rs_freshness = Freshness.MISSING
        if (
            rs_vs_ihsg_5d is not None
            and analysis_date is not None
            and analysis_date >= _IHSG_AVAILABLE_FROM
        ):
            rs_freshness = Freshness.FRESH
        # Never fabricate partial RS when window is incomplete or benchmark is
        # unavailable: MISSING -> value is None.
        if rs_freshness == Freshness.MISSING:
            rs_vs_ihsg_5d = None

        # --- Volume trend sub-signal (source-confidence-gated) ----------------
        volume_freshness = Freshness.MISSING
        if volume_trend_ratio is not None and candle_source == "stockbit":
            volume_freshness = Freshness.FRESH
        # Yahoo / yahoo_inferred volume is frequently 0 or synthetic for IDX;
        # don't score it. MISSING -> value is None.
        if volume_freshness == Freshness.MISSING:
            volume_trend_ratio = None

        return SetupEvidence(
            ticker=getattr(candidate, "ticker", None) or "",
            snapshot_date=analysis_date or self._resolve_snapshot_date(candidate),
            setup_name=setup_name,
            setup_match=match_value,
            match_strength=match_strength,
            failed_gates=failed_gates,
            trend=trend,
            rsi=rsi,
            bb_width_pctile=bb_width_pctile,
            vwap_discount_pct=vwap_discount_pct,
            vwap_pct=vwap_pct,
            rs_vs_ihsg_5d=rs_vs_ihsg_5d,
            rs_freshness=rs_freshness,
            volume_trend_ratio=volume_trend_ratio,
            volume_freshness=volume_freshness,
            candle_source=candle_source,
        )

    @staticmethod
    def _resolve_snapshot_date(candidate: Any) -> date:
        candle_date = (
            getattr(candidate, "latest_candle_date", None) if candidate is not None else None
        )
        return candle_date or date.min
