"""Map immutable pre-open learning artifacts → confirm candidates.

Field aliases (observation candidate → PreOpenPostOpenCandidate):
  entry_price        → suggested_entry
  stop_loss_price    → atr_stop
  trend_signal       → trend

Opening price is never taken from the observation. Only an explicit track
snapshot ``opening_price`` key is authoritative; mid-of-book must not masquerade
as open.

Layer: Application
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from src.domain.value_objects.pre_open_post_open_assessment import PreOpenPostOpenCandidate
from src.domain.value_objects.learning_artifacts import LearningObservation

_KNOWN_REGIMES = frozenset(
    {
        "RISK_ON",
        "NEUTRAL",
        "RISK_OFF",
        "VOLATILE",
        "BULLISH",
        "SIDEWAYS",
        "WEAK",
    }
)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_market_regime_label(
    decision_payload: Mapping[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Return (regime_label, warning) from a frozen observation payload.

    Mirrors sidecar ``load_pre_open_market_regime`` semantics: unrecognised
    labels fail closed to RISK_OFF via the warning path for callers that
    apply the same policy as the retired confirm workflow.
    """
    if not decision_payload:
        return None, None
    regime_val = decision_payload.get("market_regime")
    if regime_val is None:
        return None, None
    if isinstance(regime_val, str):
        raw = regime_val
    elif isinstance(regime_val, Mapping):
        raw = regime_val.get("regime") or regime_val.get("label")
        if raw is None:
            return None, None
        raw = str(raw)
    else:
        return None, None
    raw_upper = raw.upper()
    if raw_upper not in _KNOWN_REGIMES:
        return None, (
            f"Warning: unrecognized regime '{raw}' in observation; "
            "treating as RISK_OFF (fail-closed)."
        )
    return raw, None


def extract_opening_price_from_track_payload(
    snapshot_payload: Mapping[str, Any] | None,
) -> tuple[Decimal | None, str | None, str | None]:
    """Return (price, source, confidence) from track snapshot only.

    Uses the explicit ``opening_price`` key. Does **not** fall back to mid_price
    or best_bid (silent mid-as-open is forbidden).
    """
    if not snapshot_payload:
        return None, None, None
    if "opening_price" not in snapshot_payload:
        return None, None, None
    price = _decimal_or_none(snapshot_payload.get("opening_price"))
    if price is None:
        return None, None, None
    source = snapshot_payload.get("opening_price_source")
    confidence = snapshot_payload.get("opening_price_confidence")
    return (
        price,
        str(source) if source is not None else None,
        str(confidence) if confidence is not None else None,
    )


def reconstruct_pre_open_post_open_candidate(
    observation: LearningObservation,
    *,
    opening_price: Decimal | None,
    opening_price_source: str | None = None,
    opening_price_confidence: str | None = None,
    opening_price_timestamp: str | None = None,
) -> PreOpenPostOpenCandidate:
    """Rebuild a confirm candidate from a frozen pre-open observation + open price."""
    payload = dict(observation.decision_payload or {})
    cand = payload.get("candidate") if isinstance(payload.get("candidate"), Mapping) else {}
    if not isinstance(cand, Mapping):
        cand = {}

    ticker = str(payload.get("ticker") or cand.get("ticker") or observation.window_id).upper()
    if ":" in ticker and not cand.get("ticker"):
        # window_id form ticker:YYYY-MM-DD
        ticker = ticker.split(":", 1)[0]

    return PreOpenPostOpenCandidate(
        ticker=ticker,
        opening_price=opening_price,
        iev=_int_or_none(cand.get("iev")),
        entry_range_low=_decimal_or_none(cand.get("entry_range_low")),
        entry_range_high=_decimal_or_none(cand.get("entry_range_high")),
        suggested_entry=_decimal_or_none(cand.get("entry_price")),
        atr_stop=_decimal_or_none(cand.get("stop_loss_price")),
        trend=(str(cand["trend_signal"]) if cand.get("trend_signal") is not None else None),
        rsi=_decimal_or_none(cand.get("rsi")),
        gap_pct=_decimal_or_none(cand.get("gap_pct")),
        opening_broker_backing_tag=(
            str(cand["opening_broker_backing_tag"])
            if cand.get("opening_broker_backing_tag") is not None
            else None
        ),
        fvwap_discount_pct=_decimal_or_none(cand.get("fvwap_discount_pct")),
        opening_price_source=opening_price_source,
        opening_price_confidence=opening_price_confidence,
        opening_price_timestamp=opening_price_timestamp,
        auto_confirmed=False,
        manual_override=False,
    )


def project_pre_open_state(observation: LearningObservation) -> dict[str, Any]:
    """Frozen pre-open projection for dual-column display (not post-open action)."""
    payload = dict(observation.decision_payload or {})
    cand = payload.get("candidate") if isinstance(payload.get("candidate"), Mapping) else {}
    signal = payload.get("signal") if isinstance(payload.get("signal"), Mapping) else {}
    trade = payload.get("trade_setup") if isinstance(payload.get("trade_setup"), Mapping) else {}
    if not isinstance(cand, Mapping):
        cand = {}
    if not isinstance(signal, Mapping):
        signal = {}
    if not isinstance(trade, Mapping):
        trade = {}
    ticker = str(payload.get("ticker") or cand.get("ticker") or "").upper()
    return {
        "ticker": ticker,
        "screen_result": payload.get("screen_result"),
        "direction": signal.get("direction"),
        "entry_quality": signal.get("entry_quality"),
        "signal_score": signal.get("score"),
        "setup_action": trade.get("action"),
        "entry_range_low": cand.get("entry_range_low"),
        "entry_range_high": cand.get("entry_range_high"),
        "entry_price": cand.get("entry_price"),
        "stop_loss_price": cand.get("stop_loss_price"),
        "trend_signal": cand.get("trend_signal"),
    }


def format_sampled_at_iso(sampled_at: datetime | None) -> str | None:
    if sampled_at is None:
        return None
    return sampled_at.isoformat()
