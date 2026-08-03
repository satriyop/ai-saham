"""ADR-066 Slice 4: preopen_screen cohort projection contract."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from src.application.dto.accumulation_agent import AgentStageKind
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)
from src.application.services.agent_preopen_screen_context import (
    COHORT_TOP_N,
    SCHEMA_ID,
    AgentPreOpenScreenRawInput,
    build_agent_preopen_screen_context,
)
from src.application.services.agent_stage_context import build_agent_stage_context

pytestmark = pytest.mark.agent


def _cand(ticker: str, **kwargs):
    return SimpleNamespace(
        ticker=ticker,
        iep=kwargs.get("iep", 1000),
        iep_gap_pct=kwargs.get("iep_gap_pct", 1.5),
        iev=kwargs.get("iev", 500_000),
        delta_iev=kwargs.get("delta_iev", 10_000),
        action=kwargs.get("action", "WATCH"),
        is_ncp_locked=kwargs.get("is_ncp_locked", False),
        snapshot_date=kwargs.get("snapshot_date", date(2026, 8, 1)),
    )


def test_happy_path_top_n_and_schema() -> None:
    cands = tuple(_cand(t) for t in ["BBCA", "BBRI", "TLKM"])
    raw = AgentPreOpenScreenRawInput(
        candidates=cands,
        as_of=date(2026, 8, 1),
        capture_phase="discovery-only",
        session_source="SNAPSHOT",
        session_phase="discovery-only",
        source_is_live=False,
        ncp_authoritative=False,
        filter_policy=(("screen_kind", "preopen"),),
        row_hints=(
            ("BBCA", "WATCH", "disc", "—"),
            ("BBRI", "WATCH", "disc", "—"),
            ("TLKM", "ENTER", "LOCK", "↑"),
        ),
    )
    ctx = build_agent_preopen_screen_context(raw)
    assert ctx.schema_id == SCHEMA_ID
    assert ctx.stage_kind is AgentStageKind.PREOPEN_SCREEN
    assert ctx.cohort_total == 3
    assert ctx.shown == 3
    assert [m.ticker for m in ctx.members] == ["BBCA", "BBRI", "TLKM"]
    assert ctx.members[2].action == "ENTER"
    assert ctx.members[2].ncp == "LOCK"
    assert ctx.context_reference.startswith("sha256:")
    assert ctx.cohort_identity.startswith("sha256:")


def test_top_n_caps_at_20() -> None:
    # Four alphabetic letters (IDX-like); digits fail the ticker check.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    tickers = []
    for i in range(25):
        a, b = divmod(i, 26)
        tickers.append(f"T{alphabet[a]}{alphabet[b]}X")
    cands = tuple(_cand(t) for t in tickers)
    raw = AgentPreOpenScreenRawInput(candidates=cands, as_of=date(2026, 8, 1))
    ctx = build_agent_preopen_screen_context(raw)
    assert ctx.cohort_total == 25
    assert ctx.shown == COHORT_TOP_N
    assert len(ctx.members) == 20


def test_empty_unavailable() -> None:
    with pytest.raises(AgentContextUnavailableError, match="empty"):
        build_agent_preopen_screen_context(
            AgentPreOpenScreenRawInput(candidates=(), as_of=date(2026, 8, 1))
        )


def test_as_of_mismatch_invariant() -> None:
    a = _cand("BBCA", snapshot_date=date(2026, 8, 1))
    b = _cand("BBRI", snapshot_date=date(2026, 7, 1))
    raw = AgentPreOpenScreenRawInput(candidates=(a, b), as_of=date(2026, 8, 1))
    with pytest.raises(AgentContextInvariantError, match="as-of"):
        build_agent_preopen_screen_context(raw)


def test_facade_dispatches() -> None:
    raw = AgentPreOpenScreenRawInput(candidates=(_cand("BBCA"),), as_of=date(2026, 8, 1))
    via = build_agent_stage_context(AgentStageKind.PREOPEN_SCREEN, raw)
    direct = build_agent_preopen_screen_context(raw)
    assert via.context_reference == direct.context_reference
