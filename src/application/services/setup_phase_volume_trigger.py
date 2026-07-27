"""Volume trigger evidence for setup phase detection.

Layer: Application
Depends on: setup_phase_config DTOs + stdlib only.
"""

from __future__ import annotations

from typing import Any

from src.application.services.setup_phase_config import (
    VolumeTriggerEvidence,
    VolumeTriggerValidityConfig,
)


def _unavailable_volume_evidence(reasons: list[str]) -> VolumeTriggerEvidence:
    return VolumeTriggerEvidence(
        dry_up_ratio=None,
        expansion_ratio=None,
        dry_up_confirmed=False,
        expansion_confirmed=False,
        volume_trigger_confirmed=False,
        data_valid=False,
        unavailable_reasons=tuple(reasons),
    )


def volume_trigger_evidence(
    candles: list[Any],
    *,
    setup_evidence: Any | None,
    cfg: VolumeTriggerValidityConfig,
) -> VolumeTriggerEvidence:
    ticker = getattr(setup_evidence, "ticker", None) or (
        getattr(candles[-1], "ticker", None) if candles else None
    )
    source = getattr(setup_evidence, "candle_source", None)
    source_reason = _volume_source_unavailable_reason(
        ticker=ticker,
        source=source,
        cfg=cfg,
    )
    if source_reason is not None:
        return _unavailable_volume_evidence([source_reason])

    reference_total = cfg.dry_up_reference_sessions
    lookback = cfg.dry_up_lookback_sessions
    # dry_up_reference_sessions is the reference+dry-up window size (matching
    # the min_valid_20d_sessions/zero_volume_tolerance data-quality check,
    # unchanged below). The latest session is a standalone expansion
    # candidate reserved OUTSIDE that window — a spike on the latest session
    # must not dilute its own baseline — so one extra candle is required
    # beyond reference_total, and reference_window ends up sized exactly
    # reference_total - lookback (matching the documented contract).
    total_required = reference_total + 1
    if len(candles) < total_required:
        return _unavailable_volume_evidence(
            [
                f"volume trigger unavailable: required {total_required} sessions, "
                f"found {len(candles)}"
            ]
        )
    if lookback <= 0 or lookback >= reference_total:
        return _unavailable_volume_evidence(
            ["volume trigger unavailable: invalid dry-up window configuration"]
        )

    quality_window = candles[-reference_total:]
    zero_volume = sum(1 for candle in quality_window if int(candle.volume) <= 0)
    valid_sessions = reference_total - zero_volume
    if valid_sessions < cfg.min_valid_20d_sessions or zero_volume > cfg.zero_volume_tolerance:
        return _unavailable_volume_evidence(
            ["volume trigger unavailable: insufficient valid 20d volume sessions"]
        )

    window = candles[-total_required:]
    latest = window[-1]
    dry_up_window = window[-(lookback + 1) : -1]
    reference_window = window[: -(lookback + 1)]

    reference_avg = _avg_volume(reference_window)
    dry_up_avg = _avg_volume(dry_up_window)
    if reference_avg <= 0:
        return _unavailable_volume_evidence(
            ["volume trigger unavailable: invalid reference baseline"]
        )
    if dry_up_avg <= 0:
        return _unavailable_volume_evidence(["volume trigger unavailable: invalid dry-up baseline"])

    dry_up_ratio = round(dry_up_avg / reference_avg, 4)
    expansion_ratio = round(float(latest.volume) / dry_up_avg, 4)

    dry_up_confirmed = dry_up_ratio <= cfg.dry_up_max_ratio
    expansion_confirmed = expansion_ratio >= cfg.expansion_min_ratio
    if expansion_confirmed and cfg.expansion_requires_positive_close:
        expansion_confirmed = latest.close > latest.open

    return VolumeTriggerEvidence(
        dry_up_ratio=dry_up_ratio,
        expansion_ratio=expansion_ratio,
        dry_up_confirmed=dry_up_confirmed,
        expansion_confirmed=expansion_confirmed,
        volume_trigger_confirmed=dry_up_confirmed and expansion_confirmed,
        data_valid=True,
        unavailable_reasons=(),
    )


def _volume_source_unavailable_reason(
    *,
    ticker: str | None,
    source: str | None,
    cfg: VolumeTriggerValidityConfig,
) -> str | None:
    if not cfg.require_trusted_volume:
        return None
    source_key = (source or "").strip().lower()
    if _is_benchmark_ticker(ticker):
        trusted = {str(value).strip().lower() for value in cfg.trusted_benchmark_volume_sources}
        if source_key not in trusted:
            return (
                f"volume trigger unavailable: benchmark source {source or 'missing'} is not trusted"
            )
        return None
    if source_key in {"synthetic", "yahoo_inferred", "missing"}:
        return f"volume trigger unavailable: synthetic/missing source {source_key}"
    return None


def _is_benchmark_ticker(ticker: str | None) -> bool:
    if not ticker:
        return False
    key = ticker.upper().replace(".JK", "")
    return key in {"IHSG", "^JKSE", "JKSE", "COMPOSITE"}


def _avg_volume(candles: list[Any]) -> float:
    if not candles:
        return 0.0
    return sum(float(c.volume) for c in candles) / len(candles)
