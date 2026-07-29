"""
Application-owned JSON payloads for `saham screen accum`.

Adapters (CLI/TUI) call these builders and dump the envelope; they must not
reassemble accumulation metadata, status, or related_actions themselves.

Layer: Application
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.application.dto.accumulation_screen import AccumulationScreenResponse
from src.application.dto.screen_contract import (
    ScreenSubjectKind,
    build_screen_envelope,
    default_screen_fetch_hint,
    related_actions_for_accum,
    resolve_accum_result_status,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.screen_accum_result_projector import (
    ScreenAccumMultiProjection,
    ScreenAccumSingleProjection,
)
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistResult,
)


def _effective_session_payload(
    session: EffectiveMarketSession | None,
) -> dict[str, Any] | None:
    if session is None:
        return None
    return session.to_dict()


def build_accum_single_data(
    *,
    universe_label: str,
    response: AccumulationScreenResponse,
    projection: ScreenAccumSingleProjection,
    effective_session: EffectiveMarketSession | None = None,
    warnings: Sequence[str] = (),
    strategy_name: str | None = None,
    strategy_signals: Mapping[str, str] | None = None,
    save_result: SaveScreenWatchlistResult | None = None,
    diagnostic_evidence_by_ticker: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verb-specific ``data`` payload for a single-window accumulation screen."""
    saved_name = save_result.name if save_result is not None else None
    data: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "accumulation_screen",
        "universe": universe_label,
        "screened_at": str(response.screened_at),
        "window_days": response.window_days,
        "total_checked": response.total_tickers_checked,
        "skipped": response.tickers_skipped,
        "provider": response.provider,
        "effective_session": _effective_session_payload(effective_session),
        "candidates": [c.to_dict() for c in projection.candidates],
        "warnings": list(warnings),
        "partial_result": response.tickers_skipped > 0,
        **projection.to_dict(),
        "related_actions": related_actions_for_accum(
            tickers=[c.ticker for c in projection.candidates],
            saved_watchlist_name=saved_name,
        ),
    }
    if strategy_name:
        data["strategy_name"] = strategy_name
        data["strategy_signals"] = dict(strategy_signals or {})
    if save_result is not None:
        data["saved_watchlist"] = {
            "name": save_result.name,
            "saved_count": save_result.saved_count,
        }
    if diagnostic_evidence_by_ticker:
        data["diagnostic_evidence"] = {
            key: (val.to_dict() if hasattr(val, "to_dict") else val)
            for key, val in diagnostic_evidence_by_ticker.items()
        }
    return data


def build_accum_single_envelope(
    *,
    universe_label: str,
    response: AccumulationScreenResponse,
    projection: ScreenAccumSingleProjection,
    effective_session: EffectiveMarketSession | None = None,
    warnings: Sequence[str] = (),
    strategy_name: str | None = None,
    strategy_signals: Mapping[str, str] | None = None,
    save_result: SaveScreenWatchlistResult | None = None,
    diagnostic_evidence_by_ticker: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Full ADR-046 envelope for single-window ``screen accum`` JSON."""
    data = build_accum_single_data(
        universe_label=universe_label,
        response=response,
        projection=projection,
        effective_session=effective_session,
        warnings=warnings,
        strategy_name=strategy_name,
        strategy_signals=strategy_signals,
        save_result=save_result,
        diagnostic_evidence_by_ticker=diagnostic_evidence_by_ticker,
    )
    return build_screen_envelope(
        verb="accum",
        status=resolve_accum_result_status(result_count=len(projection.candidates)),
        subject_kind=ScreenSubjectKind.UNIVERSE,
        subject_id=universe_label,
        as_of=response.screened_at,
        source="accumulation_screen",
        scope="single",
        window_days=response.window_days,
        fetch_hint=default_screen_fetch_hint(universe=universe_label),
        data=data,
    )


def build_accum_multi_data(
    *,
    universe_label: str,
    projection: ScreenAccumMultiProjection,
    multi_results: Mapping[int, AccumulationScreenResponse],
    effective_session: EffectiveMarketSession | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Verb-specific ``data`` payload for multi-window accumulation screen."""
    tickers_payload: dict[str, Any] = {}
    for row in projection.rows:
        entry = row.to_dict()
        entry.update(entry.pop("windows"))
        entry.pop("ticker", None)
        tickers_payload[row.ticker] = entry

    partial_result = any(resp.tickers_skipped > 0 for resp in multi_results.values())
    return {
        "schema_version": 1,
        "artifact_type": "accumulation_screen_multi",
        "mode": "multi",
        "universe": universe_label,
        "windows": [f"{w}_sessions" for w in projection.resolved_windows],
        "screened_at": str(projection.screened_at),
        "effective_session": _effective_session_payload(effective_session),
        "tickers": tickers_payload,
        "warnings": list(warnings),
        "partial_result": partial_result,
        **projection.to_dict(),
        "related_actions": related_actions_for_accum(
            tickers=[row.ticker for row in projection.rows],
        ),
    }


def build_accum_multi_envelope(
    *,
    universe_label: str,
    projection: ScreenAccumMultiProjection,
    multi_results: Mapping[int, AccumulationScreenResponse],
    effective_session: EffectiveMarketSession | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Full ADR-046 envelope for multi-window ``screen accum`` JSON."""
    data = build_accum_multi_data(
        universe_label=universe_label,
        projection=projection,
        multi_results=multi_results,
        effective_session=effective_session,
        warnings=warnings,
    )
    return build_screen_envelope(
        verb="accum",
        status=resolve_accum_result_status(result_count=len(projection.rows)),
        subject_kind=ScreenSubjectKind.UNIVERSE,
        subject_id=universe_label,
        as_of=projection.screened_at,
        source="accumulation_screen",
        scope="multi",
        fetch_hint=default_screen_fetch_hint(universe=universe_label),
        data=data,
    )
