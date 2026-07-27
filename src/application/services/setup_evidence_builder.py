"""
SetupEvidenceBuilder — application service.

Translates an existing SetupEvaluation and AccumulationCandidate into a
diagnostic SetupEvidence value object. Introduced in Phase 2 of the
SignalEngine refactor.

This service owns NO setup policy: it does not re-evaluate gates or thresholds.
The authoritative setup policy lives in EvaluateSwingSetupUseCase and
config/swing_setups.yaml. This builder only reshapes already-computed results
and applies freshness gating for the benchmark excess-return and volume
sub-signals.

Layer: Application
Depends on: domain VOs (SetupEvidence, BenchmarkExcessReturn, Freshness) +
stdlib only. No provider/repository/CLI imports.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturn
from src.domain.value_objects.factor_evidence import Freshness
from src.domain.value_objects.setup_evidence import SetupEvidence

# IHSG benchmark candle history only becomes reliable from this date. Before
# it, benchmark excess-return windows cannot be trusted regardless of what
# the calculator computed, so both horizons are forced UNAVAILABLE.
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
        benchmark_excess_return_5_session: BenchmarkExcessReturn | None = None,
        benchmark_excess_return_20_session: BenchmarkExcessReturn | None = None,
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

        # --- Entry authority metadata (explicit config; no name-guessing) ------
        setup_family = getattr(setup_eval, "family", None) if setup_eval is not None else None
        entry_authority = (
            bool(getattr(setup_eval, "entry_authority", True)) if setup_eval is not None else True
        )
        can_enter_from_phases = tuple(
            getattr(setup_eval, "can_enter_from_phases", ()) or () if setup_eval is not None else ()
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

        # --- Benchmark excess-return sub-signal (date-gated) ------------------
        # IHSG history before _IHSG_AVAILABLE_FROM is untrustworthy at the
        # source regardless of alignment, so both horizons are forced
        # UNAVAILABLE before that date — never fabricated as neutral/passed.
        date_trusted = analysis_date is not None and analysis_date >= _IHSG_AVAILABLE_FROM
        benchmark_excess_return_5_session = _gate_by_date(
            benchmark_excess_return_5_session,
            window_sessions=5,
            date_trusted=date_trusted,
        )
        benchmark_excess_return_20_session = _gate_by_date(
            benchmark_excess_return_20_session,
            window_sessions=20,
            date_trusted=date_trusted,
        )

        # --- Volume trend sub-signal (data-quality-gated) ---------------------
        volume_freshness = Freshness.MISSING
        if volume_trend_ratio is not None and not _is_synthetic_volume_source(candle_source):
            volume_freshness = Freshness.FRESH
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
            benchmark_excess_return_5_session=benchmark_excess_return_5_session,
            benchmark_excess_return_20_session=benchmark_excess_return_20_session,
            volume_trend_ratio=volume_trend_ratio,
            volume_freshness=volume_freshness,
            candle_source=candle_source,
            setup_family=setup_family,
            entry_authority=entry_authority,
            can_enter_from_phases=can_enter_from_phases,
        )

    @staticmethod
    def _resolve_snapshot_date(candidate: Any) -> date:
        candle_date = (
            getattr(candidate, "latest_candle_date", None) if candidate is not None else None
        )
        return candle_date or date.min


def _is_synthetic_volume_source(source: str | None) -> bool:
    return (source or "").strip().lower() in {"synthetic", "yahoo_inferred", "missing"}


def _gate_by_date(
    window: BenchmarkExcessReturn | None,
    *,
    window_sessions: int,
    date_trusted: bool,
) -> BenchmarkExcessReturn:
    """Never fabricate benchmark excess-return evidence: no caller-supplied
    window becomes "not computed"; an untrusted analysis date overrides
    whatever the calculator produced."""
    if window is None:
        return BenchmarkExcessReturn.unavailable(
            benchmark="IHSG",
            window_sessions=window_sessions,
            reason="not_computed",
        )
    if not date_trusted:
        return BenchmarkExcessReturn.unavailable(
            benchmark=window.benchmark,
            window_sessions=window_sessions,
            reason="ihsg_history_unreliable_before_cutoff",
        )
    return window
