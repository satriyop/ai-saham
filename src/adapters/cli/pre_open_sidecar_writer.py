"""
Sidecar artifact writer for `saham screen pre-open`.

Layer: Adapter
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.screener_result import ScreenerCandidate


def write_pre_open_sidecar(
    *,
    candidates: list[ScreenerCandidate],
    screened_date: date,
    sidecar_path: Path,
    market_regime: MarketContext | None = None,
) -> None:
    """Write session sidecar JSON so `saham trade confirm` can read it."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "artifact_type": "pre_open_session",
        "screened_at": str(screened_date),
        "market_regime": market_regime.to_dict() if market_regime else None,
        "candidates": [
            {
                "ticker": c.ticker,
                "iev": c.iev,
                "gap_pct": str(c.gap_pct) if c.gap_pct is not None else None,
                "entry_range_low": str(c.entry_range_low) if c.entry_range_low else None,
                "entry_range_high": str(c.entry_range_high) if c.entry_range_high else None,
                "suggested_entry": str(c.entry_price) if c.entry_price else None,
                "atr_stop": str(c.stop_loss_price) if c.stop_loss_price else None,
                "trend": c.trend_signal,
                "rsi": str(c.rsi) if c.rsi else None,
                "opening_broker_backing_tag": c.opening_broker_backing_tag,
                "opening_broker_backing_score": c.opening_broker_backing_score,
                "opening_broker_buy_streak": c.opening_broker_buy_streak,
                "foreign_vwap": str(c.foreign_vwap) if c.foreign_vwap else None,
                "fvwap_discount_pct": (
                    c.fvwap_discount_pct if c.fvwap_discount_pct is not None else None
                ),
                "prev_high": float(c.prev_high) if c.prev_high else None,
                "prev_low": float(c.prev_low) if c.prev_low else None,
                "ticker_notation": c.ticker_notation.to_dict() if c.ticker_notation else None,
            }
            for c in candidates
        ],
    }
    with open(sidecar_path, "w") as f:
        json.dump(data, f, indent=2)
