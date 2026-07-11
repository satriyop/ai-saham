"""
Intraday confirmation session sidecar file I/O and parsing.

Owns loading/writing of pre-open session sidecar JSON, confirmation sidecar JSON,
track file parsing, and market regime extraction.

Layer: Application
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.application.use_case.resolve_opening_prices_use_case import (
    OpeningPriceObservation,
)
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmation,
    IntradayConfirmationCandidate,
)

_KNOWN_REGIMES = frozenset({
    "RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE",
    "BULLISH", "SIDEWAYS", "WEAK",
})


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _extract_observed_price(tdata) -> tuple[Decimal, str, str] | None:
    """Extract (price, source, confidence) from a track-file ticker entry.

    Mirrors the logic from opening_grade_use_case._extract_observed_price.
    """
    if not isinstance(tdata, dict):
        return None

    if tdata.get("opening_price") is not None:
        return (
            Decimal(str(tdata["opening_price"])),
            tdata.get("opening_price_source") or "opening_price",
            tdata.get("opening_price_confidence") or "MEDIUM",
        )

    order_book = tdata.get("order_book")
    if isinstance(order_book, dict) and order_book.get("last_price") is not None:
        return (
            Decimal(str(order_book["last_price"])),
            "order_book_lastprice",
            "MEDIUM",
        )

    if tdata.get("mid_price") is not None:
        return (
            Decimal(str(tdata["mid_price"])),
            tdata.get("mid_price_source") or "top_of_book_midpoint",
            tdata.get("mid_price_confidence") or "LOW",
        )

    return None


def load_intraday_confirmation_candidates(
    session_path: Path,
    opening_prices: dict[str, Decimal],
    observations: dict[str, OpeningPriceObservation] | None = None,
) -> tuple[date, list[IntradayConfirmationCandidate], dict[str, dict]]:
    """Load confirmation candidates from a pre-open session sidecar JSON file.

    Returns (screened_at, candidates, extras) where extras preserves
    display-oriented metadata per ticker.

    Raises:
        FileNotFoundError: session_path does not exist.
        json.JSONDecodeError: file is not valid JSON.
        KeyError: missing required field(s).
    """
    with open(session_path) as f:
        data = json.load(f)

    screened_at = date.fromisoformat(data["screened_at"])
    candidates: list[IntradayConfirmationCandidate] = []
    extras: dict[str, dict] = {}
    observations = observations or {}

    for row in data.get("candidates", []):
        ticker = str(row["ticker"]).upper()
        observation = observations.get(ticker)
        candidates.append(
            IntradayConfirmationCandidate(
                ticker=ticker,
                opening_price=opening_prices.get(ticker),
                iev=row.get("iev"),
                entry_range_low=_decimal_or_none(row.get("entry_range_low")),
                entry_range_high=_decimal_or_none(row.get("entry_range_high")),
                suggested_entry=_decimal_or_none(row.get("suggested_entry")),
                atr_stop=_decimal_or_none(row.get("atr_stop")),
                trend=row.get("trend"),
                rsi=_decimal_or_none(row.get("rsi")),
                gap_pct=_decimal_or_none(row.get("gap_pct")),
                opening_broker_backing_tag=row.get("opening_broker_backing_tag"),
                fvwap_discount_pct=_decimal_or_none(row.get("fvwap_discount_pct")),
                opening_price_source=observation.source if observation else None,
                opening_price_confidence=observation.confidence if observation else None,
                opening_price_timestamp=(
                    observation.timestamp.isoformat()
                    if observation and observation.timestamp
                    else None
                ),
                auto_confirmed=observation.auto_confirmed if observation else False,
                manual_override=observation.manual_override if observation else False,
            )
        )
        extras[ticker] = {
            "prev_high": row.get("prev_high"),
            "prev_low": row.get("prev_low"),
            "entry_range_low": row.get("entry_range_low"),
            "entry_range_high": row.get("entry_range_high"),
            "opening_broker_backing_tag": row.get("opening_broker_backing_tag"),
            "fvwap_discount_pct": row.get("fvwap_discount_pct"),
            "opening_price_source": observation.source if observation else None,
            "opening_price_confidence": observation.confidence if observation else None,
            "opening_price_reason": observation.reason if observation else None,
            "auto_confirmed": observation.auto_confirmed if observation else False,
            "manual_override": observation.manual_override if observation else False,
        }

    return screened_at, candidates, extras


def load_intraday_confirmation_tickers(
    session_path: Path,
) -> tuple[date, list[str]]:
    """Load confirmation tickers from a pre-open session sidecar JSON file.

    Returns (screened_at, tickers).

    Raises:
        FileNotFoundError: session_path does not exist.
        json.JSONDecodeError: file is not valid JSON.
        KeyError: missing required field(s).
    """
    with open(session_path) as f:
        data = json.load(f)
    screened_at = date.fromisoformat(data["screened_at"])
    tickers = [str(row["ticker"]).upper() for row in data.get("candidates", [])]
    return screened_at, tickers


def load_pre_open_market_regime(
    session_path: Path,
) -> tuple[str | None, str | None]:
    """Extract market regime label from a pre-open sidecar.

    Returns (regime, None) when the regime is recognised,
    (None, warning) when unrecognised,
    (None, None) when absent or unreadable.

    The warning string matches the current CLI output exactly.
    """
    if not session_path.exists():
        return None, None

    try:
        with open(session_path) as f:
            sidecar_data = json.load(f)
    except Exception:
        return None, None

    regime_dict = sidecar_data.get("market_regime")
    if not regime_dict or not isinstance(regime_dict, dict):
        return None, None

    raw = regime_dict.get("regime") or regime_dict.get("label")
    if raw is None:
        return None, None

    raw_upper = raw.upper()
    if raw_upper not in _KNOWN_REGIMES:
        return None, (
            f"Warning: unrecognized regime '{raw}' in sidecar; "
            "treating as RISK_OFF (fail-closed)."
        )

    return raw, None


def write_intraday_confirmation_sidecar(
    confirmations: tuple[IntradayConfirmation, ...],
    confirmed_date: date,
    max_stop_pct: Decimal,
    output_path: Path,
) -> None:
    """Write intraday confirmation results to a sidecar JSON file.

    Preserves the exact JSON contract including artifact_type, confirmed_at,
    and all per-confirmation fields with current numeric/string formatting.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "artifact_type": "intraday_confirmation",
        "confirmed_at": str(confirmed_date),
        "max_stop_pct": str(max_stop_pct),
        "confirmations": [
            {
                "ticker": c.ticker,
                "decision": c.decision.value,
                "opening_price": str(c.opening_price) if c.opening_price else None,
                "planned_entry": str(c.planned_entry) if c.planned_entry else None,
                "stop_loss_price": str(c.stop_loss_price) if c.stop_loss_price else None,
                "stop_pct": str(c.stop_pct) if c.stop_pct is not None else None,
                "reasons": list(c.reasons),
                "iev": c.iev,
                "trend": c.trend,
                "rsi": str(c.rsi) if c.rsi is not None else None,
                "gap_pct": str(c.gap_pct) if c.gap_pct is not None else None,
                "opening_broker_backing_tag": c.opening_broker_backing_tag,
                "fvwap_discount_pct": (
                    str(c.fvwap_discount_pct)
                    if c.fvwap_discount_pct is not None
                    else None
                ),
                "opening_price_source": c.opening_price_source,
                "opening_price_confidence": c.opening_price_confidence,
                "opening_price_timestamp": c.opening_price_timestamp,
                "auto_confirmed": c.auto_confirmed,
                "manual_override": c.manual_override,
            }
            for c in confirmations
        ],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_opening_prices_from_track_file(
    track_file: Path,
    tickers: list[str],
) -> dict[str, OpeningPriceObservation]:
    """Resolve opening prices from a track_*.json offline tracking file.

    Returns a dict mapping ticker -> OpeningPriceObservation for tickers
    that have usable price data in the track file. Tickers without data
    are omitted.

    Raises:
        FileNotFoundError: track_file does not exist.
        json.JSONDecodeError: file is not valid JSON.
    """
    with open(track_file) as f:
        track_data = json.load(f)

    captured_at_str = track_data.get("captured_at")
    captured_at_dt: datetime | None = None
    if captured_at_str:
        try:
            captured_at_dt = datetime.fromisoformat(captured_at_str)
        except Exception:
            pass

    track_tickers = track_data.get("tickers", {})
    observations: dict[str, OpeningPriceObservation] = {}

    for ticker in tickers:
        tdata = track_tickers.get(ticker)
        observed = _extract_observed_price(tdata)
        if observed is not None:
            price_val, source_val, confidence_val = observed
            observations[ticker] = OpeningPriceObservation(
                ticker=ticker,
                price=price_val,
                source=source_val,
                confidence=confidence_val,
                timestamp=captured_at_dt,
                reason=f"Resolved offline from track file {track_file.name}",
                auto_confirmed=True,
                manual_override=False,
            )

    return observations
