"""
OpeningSnapshotUseCase — NCP-locked pre-open screener capture for the learning loop.

Runs the full PreOpenScreenUseCase once at the NCP-locked window (08:57 WIB) and
saves the result to data/opening/YYYYMMDD/snapshot.json for later accuracy grading.

Also writes the standard .last-session.json sidecar so the `saham trade confirm`
workflow is unaffected.

Layer: Application
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.pre_open_screen import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenUseCase,
)
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    NCP_LOCK_TIME,
    OPEN_SESSION_END,
)
from src.domain.value_objects.idx_market import (
    PRE_OPEN_START as PRE_NCP_START,
)
from src.domain.value_objects.idx_market import (
    REGULAR_OPEN as REGULAR_OPEN_TIME,
)

OPENING_DATA_DIR = Path("data/opening")


@dataclass(frozen=True)
class OpeningSnapshotRequest:
    config: PreOpenScreenConfig
    run_date: date | None = None
    iep_lookup: "dict[str, int] | None" = None


class OpeningSnapshotUseCase:
    """Capture NCP-locked screener signals and persist to data/opening/YYYYMMDD/snapshot.json."""

    def __init__(
        self,
        browser: BrowserDataProvider,
        repository: MarketDataRepository,
        registry: IndicatorRegistry,
        broker_repository=None,
        ticker_notation_provider=None,
    ) -> None:
        self._screen_uc = PreOpenScreenUseCase(
            browser=browser,
            repository=repository,
            registry=registry,
            broker_repository=broker_repository,
            ticker_notation_provider=ticker_notation_provider,
        )

    def execute(self, request: OpeningSnapshotRequest) -> dict:
        now = datetime.now(IDX_TIMEZONE)
        run_date = request.run_date or now.date()
        phase = classify_opening_capture_phase(now)
        is_ncp = phase == "NCP_LOCKED"

        response = self._screen_uc.execute(
            PreOpenScreenRequest(config=request.config, run_date=run_date)
        )
        candidates = response.result.candidates

        iep_lookup = request.iep_lookup or {}

        candidates_out = []
        for c in candidates:
            entry = float(c.entry_price) if c.entry_price else None
            stop = float(c.stop_loss_price) if c.stop_loss_price else None
            one_r = round(entry - stop, 2) if entry and stop else None
            candidates_out.append({
                "ticker": c.ticker,
                "iev": c.iev,
                "iep": iep_lookup.get(c.ticker),
                "entry_range_low": float(c.entry_range_low) if c.entry_range_low else None,
                "entry_range_high": float(c.entry_range_high) if c.entry_range_high else None,
                "suggested_entry": entry,
                "atr_stop": stop,
                "one_r": one_r,
                "trend": c.trend_signal,
                "rsi": round(float(c.rsi), 2) if c.rsi else None,
                "atr": round(float(c.atr), 2) if c.atr else None,
                "accum_tag": c.accum_tag,
                "accum_score": round(c.accum_score, 1) if c.accum_score is not None else None,
                "iev_intensity": round(c.iev_intensity, 3) if c.iev_intensity is not None else None,
                "unusual_volume": c.unusual_volume,
                # bid_offer_imbalance: NCP-locked pre-open order book ratio
                # bid_lots / (bid_lots + offer_lots) at 08:57
                # >0.6 = buyers dominating (committed demand), <0.4 = sellers dominating
                "bid_pressure_preopen": c.bid_offer_imbalance,
                "ticker_notation": c.ticker_notation.to_dict() if c.ticker_notation else None,
                "verdict": self._verdict(c, request.config.min_bid_pressure_preopen),
            })

        snapshot = {
            "captured_at": now.isoformat(),
            "date": str(run_date),
            "capture_phase": phase,
            "capture_valid_for_opening_prediction": phase in ("PRE_NCP", "NCP_LOCKED"),
            "capture_confidence": _capture_confidence(phase),
            "is_ncp_locked": is_ncp,
            "candidates": candidates_out,
            "warnings": response.warnings,
        }

        out_dir = OPENING_DATA_DIR / run_date.strftime("%Y%m%d")
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "snapshot.json", "w") as f:
            json.dump(snapshot, f, indent=2)

        return snapshot

    @staticmethod
    def _verdict(candidate, min_bp: float = 0.0) -> str:
        """Derive PRIME/WATCH/SKIP from existing candidate signals."""
        trend = candidate.trend_signal or ""
        accum = candidate.accum_tag or ""
        unusual = getattr(candidate, "unusual_volume", False)
        # Weak pre-open bid pressure → insufficient conviction for a WATCH entry
        if min_bp > 0 and (candidate.bid_offer_imbalance or 0) < min_bp:
            return "SKIP"
        if trend == "BULLISH" and accum == "BACKED" and not unusual:
            return "PRIME"
        if trend in ("BULLISH", "NEUTRAL") and accum != "DISTRIBUTING":
            return "WATCH"
        return "SKIP"


def classify_opening_capture_phase(captured_at: datetime) -> str:
    """Classify a capture timestamp into deterministic IDX opening phases."""
    local = captured_at.astimezone(IDX_TIMEZONE)
    current = local.time()
    if PRE_NCP_START <= current < NCP_LOCK_TIME:
        return "PRE_NCP"
    if NCP_LOCK_TIME <= current < REGULAR_OPEN_TIME:
        return "NCP_LOCKED"
    if REGULAR_OPEN_TIME <= current <= OPEN_SESSION_END:
        return "OPEN"
    if current > OPEN_SESSION_END:
        return "POST_OPEN"
    return "OUT_OF_SESSION"


def _capture_confidence(phase: str) -> str:
    if phase == "NCP_LOCKED":
        return "HIGH"
    if phase == "PRE_NCP":
        return "MEDIUM"
    return "LOW"
