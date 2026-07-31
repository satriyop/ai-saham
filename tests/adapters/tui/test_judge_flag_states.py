"""Judge flag chips are data-contextual (not a static peach wall)."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.tui.judge_flag_states import (
    expandable_flags_available,
    judge_flag_chip_states,
    open_panels,
)


def _model(
    *,
    limited: bool = False,
    decision_lines: tuple[str, ...] = ("Decision", "line"),
    readiness: str = "flow-only",
    phase_arrow: str = "ACCUM → COMPRESS",
    cards: tuple = (),
):
    return SimpleNamespace(
        limited=limited,
        decision_lines=decision_lines,
        readiness=readiness,
        phase_arrow=phase_arrow,
        cards=cards,
    )


def test_compact_full_judge_no_chip_is_on_except_none():
    m = _model()
    states = {s.key: s for s in judge_flag_chip_states(m, detail_all=False, open_flags=set())}
    assert states["detail"].expanded is False
    assert states["stack"].available is True and states["stack"].expanded is False
    assert states["named"].available is False  # no named card
    assert states["mce"].available is False
    assert states["limited"].visible is False


def test_detail_all_only_master_is_on_not_peach_wall():
    m = _model(
        cards=(
            SimpleNamespace(key="named_setups"),
            SimpleNamespace(key="market"),
        )
    )
    states = {
        s.key: s
        for s in judge_flag_chip_states(
            m,
            detail_all=True,
            open_flags={"stack", "readiness", "named", "mce", "phase_plus"},
        )
    }
    assert states["detail"].expanded is True
    # Singles available but not all peach when master opens
    assert states["stack"].available is True and states["stack"].expanded is False
    assert states["named"].available is True and states["named"].expanded is False
    assert states["mce"].available is True and states["mce"].expanded is False
    assert states["limited"].visible is False


def test_limited_state_chip_only_when_limited():
    m = _model(limited=True, decision_lines=(), readiness="—", phase_arrow="")
    states = {s.key: s for s in judge_flag_chip_states(m, detail_all=False, open_flags=set())}
    assert states["limited"].visible is True
    assert states["limited"].warn is True
    assert states["limited"].expanded is True
    assert states["stack"].available is False


def test_open_panels_respects_availability():
    m = _model(cards=(SimpleNamespace(key="market"),))
    panels = open_panels(m, detail_all=True, open_flags=set())
    assert "stack" in panels
    assert "mce" in panels
    assert "named" not in panels
    assert expandable_flags_available(m) == {"stack", "readiness", "mce", "phase_plus"}


def test_single_chip_open_is_on():
    m = _model()
    states = {s.key: s for s in judge_flag_chip_states(m, detail_all=False, open_flags={"stack"})}
    assert states["stack"].expanded is True
    assert states["detail"].expanded is False
    assert states["readiness"].expanded is False
