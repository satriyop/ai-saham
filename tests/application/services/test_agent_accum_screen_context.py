"""ADR-066 Slice 1: accum_screen cohort projection contract."""

from __future__ import annotations

from datetime import date

import pytest

from src.application.dto.accumulation_agent import AgentStageKind
from src.application.services.agent_accum_screen_context import (
    COHORT_TOP_N,
    SCHEMA_ID,
    AgentAccumScreenRawInput,
    build_agent_accum_screen_context,
)
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)
from src.application.services.agent_stage_context import build_agent_stage_context
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def test_happy_path_top_n_bound_and_schema() -> None:
    # Build N candidates with distinct tickers by patching after make
    from dataclasses import replace

    cands = []
    for ticker in ["BBCA", "BBRI", "TLKM", "ASII", "BMRI"]:
        c = make_candidate()
        c = replace(c, ticker=ticker)
        c = replace(c, trade_setup=replace(c.trade_setup, ticker=ticker))
        signal = c.signal_assessment.assessment
        response = replace(
            c.signal_assessment,
            ticker=ticker,
            assessment=replace(signal, ticker=ticker),
        )
        accum = replace(c.accum_score_breakdown, ticker=ticker)
        cands.append(replace(c, signal_assessment=response, accum_score_breakdown=accum))

    raw = AgentAccumScreenRawInput(
        candidates=tuple(cands),
        universe="lq45",
        window_days=7,
        sort_by="signal",
        top_limit=20,
        as_of=date(2026, 8, 1),
        regime="SIDEWAYS",
        filter_policy=(("sort_by", "signal"), ("window_days", 7)),
    )
    ctx = build_agent_accum_screen_context(raw)
    assert ctx.schema_id == SCHEMA_ID
    assert ctx.stage_kind is AgentStageKind.ACCUM_SCREEN
    assert ctx.cohort_total == 5
    assert ctx.shown == 5
    assert ctx.shown == min(COHORT_TOP_N, ctx.cohort_total)
    assert [m.ticker for m in ctx.members] == ["BBCA", "BBRI", "TLKM", "ASII", "BMRI"]
    assert all(m.as_of == ctx.as_of for m in ctx.members)
    assert ctx.context_reference.startswith("sha256:")
    assert ctx.cohort_identity.startswith("sha256:")
    assert ctx.session_subject.startswith("ACCUM_SCREEN:")


def test_top_n_caps_at_20() -> None:
    cands = []
    for _ in range(25):
        # Same candidate shape; only board order / top-N bound is under test.
        cands.append(make_candidate())
    raw = AgentAccumScreenRawInput(
        candidates=tuple(cands),
        universe="lq45",
        window_days=7,
        as_of=date(2026, 8, 1),
    )
    ctx = build_agent_accum_screen_context(raw)
    assert ctx.cohort_total == 25
    assert ctx.shown == 20
    assert len(ctx.members) == 20
    assert ctx.members[0].rank == 1
    assert ctx.members[-1].rank == 20


def test_empty_board_unavailable() -> None:
    with pytest.raises(AgentContextUnavailableError, match="empty board"):
        build_agent_accum_screen_context(
            AgentAccumScreenRawInput(candidates=(), universe="lq45", window_days=7)
        )


def test_missing_universe_unavailable() -> None:
    with pytest.raises(AgentContextUnavailableError, match="universe"):
        build_agent_accum_screen_context(
            AgentAccumScreenRawInput(
                candidates=(make_candidate(),),
                universe="  ",
                window_days=7,
            )
        )


def test_member_as_of_mismatch_invariant() -> None:
    from dataclasses import replace

    a = make_candidate()
    b = make_candidate()
    b = replace(
        b,
        trade_setup=replace(b.trade_setup, snapshot_date=date(2026, 7, 1)),
        signal_assessment=replace(
            b.signal_assessment,
            assessment=replace(b.signal_assessment.assessment, snapshot_date=date(2026, 7, 1)),
        ),
        accum_score_breakdown=replace(b.accum_score_breakdown, snapshot_date=date(2026, 7, 1)),
        latest_candle_date=date(2026, 7, 1),
        latest_broker_date=date(2026, 7, 1),
    )
    raw = AgentAccumScreenRawInput(
        candidates=(a, b),
        universe="lq45",
        window_days=7,
        as_of=date(2026, 8, 1),
    )
    with pytest.raises(AgentContextInvariantError, match="as-of"):
        build_agent_accum_screen_context(raw)


def test_facade_dispatches_accum_screen() -> None:
    raw = AgentAccumScreenRawInput(
        candidates=(make_candidate(),),
        universe="lq45",
        window_days=7,
        as_of=date(2026, 8, 1),
    )
    via_facade = build_agent_stage_context(AgentStageKind.ACCUM_SCREEN, raw)
    direct = build_agent_accum_screen_context(raw)
    assert via_facade.context_reference == direct.context_reference
    assert via_facade.schema_id == SCHEMA_ID


def test_stable_hash_for_same_input() -> None:
    raw = AgentAccumScreenRawInput(
        candidates=(make_candidate(),),
        universe="lq45",
        window_days=7,
        as_of=date(2026, 8, 1),
        filter_policy=(("sort_by", "signal"),),
    )
    a = build_agent_accum_screen_context(raw)
    b = build_agent_accum_screen_context(raw)
    assert a.context_reference == b.context_reference
    assert a.cohort_identity == b.cohort_identity
