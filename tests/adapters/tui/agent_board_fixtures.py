"""Board payloads with real AccumulationCandidate sources for agent TUI tests.

ADR-066 builds Judge context at cockpit open; SimpleNamespace fakes fail the
typed stage facade. Use this for agent commentary / golden UX pilots.
"""

from __future__ import annotations

from types import SimpleNamespace

from tests.application.services.test_agent_accumulation_context import make_candidate


def agent_accum_payload():
    """Minimal accum board payload whose row.source is a full Judge candidate."""
    candidate = make_candidate()
    return SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[candidate],
            window_days=7,
            data_as_of={"latest_candle_date": candidate.trade_setup.snapshot_date},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        effective_session=None,
        market_context=None,
        multi_projection=None,
        warnings=(),
    )
