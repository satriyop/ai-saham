"""Judge density: brief ↔ detail (CLI --detail), not multi-chip wall."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.tui.judge_flag_states import expandable_flags_available, open_panels


def _model(
    *,
    decision_lines: tuple[str, ...] = ("Decision", "line"),
    readiness: str = "flow-only",
    phase_arrow: str = "ACCUM → COMPRESS",
    cards: tuple = (),
):
    return SimpleNamespace(
        limited=False,
        decision_lines=decision_lines,
        readiness=readiness,
        phase_arrow=phase_arrow,
        cards=cards,
    )


def test_brief_opens_no_detail_panels():
    m = _model(cards=(SimpleNamespace(key="market"),))
    assert open_panels(m, detail_all=False, open_flags={"stack", "mce"}) == set()


def test_detail_opens_all_available_sections():
    m = _model(
        cards=(
            SimpleNamespace(key="named_setups"),
            SimpleNamespace(key="market"),
        )
    )
    panels = open_panels(m, detail_all=True, open_flags=set())
    assert panels == {"stack", "readiness", "named", "mce", "phase_plus"}
    assert expandable_flags_available(m) == panels


def test_detail_omits_missing_sections():
    m = _model(decision_lines=(), readiness="—", phase_arrow="", cards=())
    assert open_panels(m, detail_all=True, open_flags=set()) == set()
