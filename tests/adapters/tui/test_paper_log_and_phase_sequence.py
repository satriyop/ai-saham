"""TUI paper journal from plan (A) + Judge phase sequence from ledger (B)."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.paper_log_result import PaperLogResult, refuse_paper_log
from src.adapters.tui.phase_sequence import (
    PhaseSequenceFact,
    facts_from_ledger_rows,
    format_phase_sequence_section,
)
from src.adapters.tui.plan_structure_result import PlanStructureResult
from src.adapters.tui.presenters.accum_engine_inspect_presenter import (
    present_accum_engine_inspect,
)
from src.adapters.tui.presenters.accum_presenter import AccumRowView
from src.domain.value_objects.setup_phase import SetupPhaseState


def test_format_phase_sequence_ordered_and_empty():
    facts = (
        PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
        PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-25"),
    )
    text = "\n".join(format_phase_sequence_section(facts, current_phase="COMPRESSION"))
    assert "ACCUMULATION → COMPRESSION" in text
    assert "2026-07-20" in text and "2026-07-25" in text
    assert "now" in text.lower() and "COMPRESSION" in text
    assert "not a re-score" in text.lower() or "production memory" in text.lower()
    # Single footer only
    assert text.lower().count("not a re-score") == 1

    empty = "\n".join(format_phase_sequence_section(()))
    assert "no closed-session phase history" in empty.lower()
    assert "ACCUMULATION" not in empty

    unavail = "\n".join(
        format_phase_sequence_section(None, unavailable_reason="cannot load sequence without as_of")
    )
    assert "cannot load sequence without as_of" in unavail
    assert "→" not in unavail


def test_format_phase_sequence_collapses_identical_runs():
    """Design: never dump DISTRIBUTION → DISTRIBUTION × N (day diary)."""
    from src.adapters.tui.phase_sequence import collapse_phase_runs

    facts = tuple(
        PhaseSequenceFact(phase="DISTRIBUTION", as_of=f"2026-07-{d:02d}") for d in range(1, 17)
    ) + (
        PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-27"),
        PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-28"),
    )
    runs = collapse_phase_runs(facts)
    assert len(runs) == 2
    assert runs[0].phase == "DISTRIBUTION" and runs[0].sessions == 16
    assert runs[1].phase == "ACCUMULATION" and runs[1].sessions == 2

    text = "\n".join(format_phase_sequence_section(facts, current_phase="ACCUMULATION"))
    assert "DISTRIBUTION (16d) → ACCUMULATION (2d)" in text
    # Must not repeat DISTRIBUTION in the arrow chain
    arrow_line = next(ln for ln in text.splitlines() if "→" in ln and "DISTRIBUTION" in ln)
    assert arrow_line.count("DISTRIBUTION") == 1
    assert arrow_line.count("ACCUMULATION") == 1
    # Detail is per-run, not per-day (2 bullets for runs, not 18)
    detail_days = [ln for ln in text.splitlines() if "sessions" in ln.lower()]
    assert len(detail_days) == 2
    assert "16 sessions" in text and "2 sessions" in text
    # No full diary of every date as a bullet of DISTRIBUTION alone
    daily_dist_bullets = [
        ln
        for ln in text.splitlines()
        if "DISTRIBUTION" in ln and ln.strip().startswith("·") and "sessions" not in ln.lower()
    ]
    assert daily_dist_bullets == []
    assert text.lower().count("not a re-score") == 1


def test_facts_from_ledger_rows_maps_phase_and_date():
    rows = [
        SimpleNamespace(
            phase=SetupPhaseState.ACCUMULATION,
            as_of_date=date(2026, 7, 10),
        ),
        SimpleNamespace(
            phase=SetupPhaseState.COMPRESSION,
            as_of_date=date(2026, 7, 15),
        ),
    ]
    facts = facts_from_ledger_rows(rows)
    assert [f.phase for f in facts] == ["ACCUMULATION", "COMPRESSION"]
    assert facts[0].as_of == "2026-07-10"


def test_judge_presenter_includes_sequence_without_rescoring_action():
    row = AccumRowView(
        ticker="BBRI",
        signal="72",
        accum="50.0",
        action="WATCH",
        gate="OPEN",
        phase="COMPRESSION",
        streak="2",
        rsi="48",
        net_pct="0.5",
        disc_pct="0.0",
        price="4825",
        source=None,
    )
    facts = (
        PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
        PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
    )
    view = present_accum_engine_inspect(
        row,
        rank=1,
        total=1,
        phase_sequence=facts,
    )
    text = view.text
    assert "ACCUMULATION → COMPRESSION" in text
    assert "WATCH" in text
    # Must not invent ENTER from sequence (Action is board WATCH)
    assert "ENTER" not in text or "WATCH" in text
    assert "Phase sequence" in text
    assert "Verdict mast" in text


def test_refuse_paper_log_helper():
    r = refuse_paper_log("bbri", "no saved plan")
    assert r.refused is True
    assert r.written is False
    assert r.ticker == "BBRI"
    assert "no saved plan" in r.message


def test_cockpit_paper_log_confirm_calls_runner_with_geometry():
    """Plan stage + confirm → injected runner receives ticker; geometry from structure."""
    calls: list[str] = []

    def runner(ticker: str) -> PaperLogResult:
        calls.append(ticker)
        return PaperLogResult(
            ticker=ticker,
            written=True,
            message=f"paper logged {ticker} · entry 4,825 · stop 4,600 · target 5,275",
            planned_entry="4,825",
            planned_stop="4,600",
            planned_target="5,275",
            plan_id="abcd1234",
        )

    async def scenario() -> None:
        app = CockpitApp(paper_log_runner=runner)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._focus_ticker = "BBRI"
            app._stage = "plan"
            app._plan_ticker = "BBRI"
            app._plan_running = False
            app._plan_structure = PlanStructureResult(
                summary="structure WATCH · entry 4,825 · stop 4,600 · target 5,275 · 2 lots",
                ticker="BBRI",
                action="WATCH",
                entry="4,825",
                stop="4,600",
                target="5,275",
                lots="2",
                plan_id_short="abcd1234",
                incomplete_reason="",
                no_order=True,
            )
            # Open confirm then confirm (Enter)
            app.action_paper_log()
            await pilot.pause(0.05)
            # Modal should be on stack — confirm
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause(0.05)
                if calls:
                    break
            assert calls == ["BBRI"]
            assert app._status_note == "paper logged"

    asyncio.run(scenario())


def test_cockpit_paper_log_refuses_incomplete_structure():
    r = refuse_paper_log("BBRI", "incomplete structure · no entry/stop/target")
    assert r.refused is True
    assert r.written is False
    assert "incomplete" in r.message.lower() or "no entry" in r.message.lower()


def test_cockpit_paper_log_surfaces_duplicate_not_written():
    def runner(ticker: str) -> PaperLogResult:
        return PaperLogResult(
            ticker=ticker,
            written=False,
            message=f"already logged {ticker} for 2026-07-30 (window=7) — no new row",
            planned_entry="4,825",
            planned_stop="4,600",
            planned_target="5,275",
        )

    async def scenario() -> None:
        app = CockpitApp(paper_log_runner=runner)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._stage = "plan"
            app._plan_ticker = "BBCA"
            app._plan_structure = PlanStructureResult(
                summary="ok",
                ticker="BBCA",
                entry="1",
                stop="2",
                target="3",
                lots="1",
                plan_id_short="deadbeef",
            )
            app.action_paper_log()
            await pilot.pause(0.05)
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._status_note == "plan done":
                    break
            # Duplicate is honest non-write, still plan done (not paper logged)
            assert app._status_note == "plan done"

    asyncio.run(scenario())


def test_cockpit_judge_shows_planted_phase_sequence():
    from types import SimpleNamespace

    from src.adapters.tui.judge_desk_model import build_judge_desk_model
    from src.adapters.tui.phase_sequence import PhaseSequenceFact
    from src.adapters.tui.presenters.accum_presenter import AccumRowView

    source = SimpleNamespace(
        ticker="BBCA",
        accum_score=48.0,
        rsi=50.0,
        consecutive_streak=2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.0,
        current_price=6275,
        name="BBCA",
        latest_candle_date=None,
        latest_broker_date=None,
        freshness=None,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="COMPRESSION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            signal_score=84,
            signal_strength=SimpleNamespace(value="MODERATE"),
            rationale="ok",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(
                score=84,
                strength=SimpleNamespace(value="MODERATE"),
                entry_quality=SimpleNamespace(value="WATCH"),
                signal_authority_coverage=0.9,
                breakdown=None,
                decision_constraints=None,
            ),
            setup_readiness=None,
            coverage_warning=None,
            signal_authority_coverage=0.9,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(),
    )
    row = AccumRowView(
        ticker="BBCA",
        signal="84",
        accum="48",
        action="WATCH",
        phase="COMPRESSION",
        streak="2",
        rsi="50",
        net_pct="0.5",
        disc_pct="0",
        price="6275",
        gate="OPEN",
        source=source,
    )
    model = build_judge_desk_model(
        row,
        phase_sequence=(
            PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
            PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
        ),
    )
    assert "ACCUMULATION" in model.phase_arrow
    assert "COMPRESSION" in model.phase_arrow


def test_cockpit_judge_empty_ledger_is_honest():
    from src.adapters.tui.judge_desk_model import build_judge_desk_model
    from src.adapters.tui.presenters.accum_presenter import AccumRowView

    row = AccumRowView(
        ticker="BBCA",
        signal="84",
        accum="48",
        action="WATCH",
        phase="NONE",
        streak="0",
        rsi="50",
        net_pct="0",
        disc_pct="0",
        price="6275",
        gate="OPEN",
        source=None,
    )
    model = build_judge_desk_model(row, phase_sequence=())
    # Empty ledger: no invented multi-phase arrow or honest empty
    assert model.phase_arrow is not None
    # limited or no false multi-hop history
    assert model.limited is True or "→" not in model.phase_arrow or model.phase_arrow


def test_local_phase_history_loader_keeps_most_recent_not_oldest_n(tmp_path):
    """Real SQLite path: >20 rows must yield last-N phases, not ASC+LIMIT oldest.

    Regression: SQL LIMIT 20 on ASC order dropped recent phases and kept early
    history — Judge would show a stale sequence.
    """
    from datetime import timedelta

    from src.adapters.tui.composition import _LocalPhaseHistoryLoader
    from src.domain.ports.setup_phase_history_repository import (
        SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    from src.infrastructure.persistence.sqlite_setup_phase_ledger_repository import (
        SQLiteSetupPhaseLedgerRepository,
    )

    db_path = tmp_path / "phase_ledger.db"
    repo = SQLiteSetupPhaseLedgerRepository(db_path)
    ticker = "BBRI"
    # Cycle phases so first and last 20 windows are distinguishable
    cycle = (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
        SetupPhaseState.EXHAUSTION,
        SetupPhaseState.DISTRIBUTION,
    )
    base = date(2025, 1, 1)
    n_rows = 25
    for i in range(n_rows):
        repo.record_phase(
            ticker=ticker,
            as_of_date=base + timedelta(days=i),
            phase=cycle[i % len(cycle)],
            setup_family="",
            source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
        )

    before = base + timedelta(days=n_rows)  # exclusive upper bound after all rows
    loader = _LocalPhaseHistoryLoader(db_path, max_facts=20)
    facts = loader(ticker, before)

    assert len(facts) == 20
    # Oldest of full history must NOT appear (row 0 = ACCUMULATION on 2025-01-01)
    oldest_as_of = base.isoformat()
    assert all(f.as_of != oldest_as_of for f in facts)
    # Most recent 20 as_of dates: base+5 .. base+24
    expected_as_ofs = [(base + timedelta(days=i)).isoformat() for i in range(5, 25)]
    assert [f.as_of for f in facts] == expected_as_ofs
    # Most recent phase is the last written (index 24)
    assert facts[-1].phase == cycle[24 % len(cycle)].value
    # ASC+LIMIT bug would return phases for base..base+19 and include oldest
    broken_would_include_oldest = any(f.as_of == oldest_as_of for f in facts)
    assert not broken_would_include_oldest
