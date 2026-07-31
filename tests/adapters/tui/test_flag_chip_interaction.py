"""Flag chip expand contracts — pure chip + model (no full-app mount).

End-to-end chip↔stage wiring residual: one journey in accum_judge / e2e (D3/D7).
"""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.tui.judge_desk_model import build_judge_desk_model
from src.adapters.tui.phase_sequence import PhaseSequenceFact
from src.adapters.tui.preopen_inspect_model import (
    EXPANDABLE_FLAGS,
    build_preopen_inspect_model,
)
from src.adapters.tui.presenters.accum_presenter import AccumRowView
from src.adapters.tui.widgets.flag_chip import FlagChip
from src.adapters.tui.widgets.judge_desk import JudgeDesk


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(
        ticker="BBCA",
        accum_score=48.2,
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
            rationale="Signal 84",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(
                score=84,
                strength=SimpleNamespace(value="MODERATE"),
                entry_quality=SimpleNamespace(value="WATCH"),
                signal_authority_coverage=0.92,
                breakdown=None,
                decision_constraints=None,
            ),
            setup_readiness=None,
            coverage_warning=None,
            signal_authority_coverage=0.92,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(),
    )


def _row() -> AccumRowView:
    return AccumRowView(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        phase="COMPRESSION",
        streak="2",
        rsi="50",
        net_pct="0.5",
        disc_pct="0",
        price="6275",
        gate="OPEN",
        source=_candidate(),
    )


def test_flag_chip_is_focusable_control():
    chip = FlagChip("stack", "stack", id="t-chip")
    assert chip.can_focus is True
    chip.set_chip_state(available=True, expanded=False)
    assert "is-dim" not in chip.classes
    chip.set_chip_state(available=False, expanded=False)
    assert "is-dim" in chip.classes
    chip.set_chip_state(available=True, expanded=True)
    assert "is-on" in chip.classes


def test_flag_chip_activate_posts_selected():
    """Click / keyboard path posts Selected with flag_key."""
    chip = FlagChip("detail", "detail · d", id="t-detail")
    chip.set_chip_state(available=True, expanded=False)
    posted: list[str] = []

    def _capture(msg: FlagChip.Selected) -> None:
        posted.append(msg.flag_key)

    # Direct activate (same as Enter/Space/click)
    orig_post = chip.post_message

    def _post(msg):  # type: ignore[no-untyped-def]
        if isinstance(msg, FlagChip.Selected):
            posted.append(msg.flag_key)
        return orig_post(msg)

    chip.post_message = _post  # type: ignore[method-assign]
    chip._activate()
    assert posted == ["detail"]
    # Dim chips do not fire
    chip.set_chip_state(available=False, expanded=False)
    chip._activate()
    assert posted == ["detail"]


def test_judge_stack_and_detail_expandable_flags_pure():
    """stack / phase+ / detail · d availability from model — paint open set."""
    model = build_judge_desk_model(
        _row(),
        phase_sequence=(
            PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
            PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
        ),
    )
    desk = JudgeDesk()
    avail = desk._available_expandable_flags(model)
    assert "phase_plus" in avail
    if model.decision_lines:
        assert "stack" in avail

    # Pure open-set simulation (same rules as on_flag_chip_selected)
    open_flags: set[str] = set()
    detail_all = False

    def toggle(key: str) -> None:
        nonlocal detail_all, open_flags
        if key == "detail":
            detail_all = not detail_all
            open_flags = set(avail) if detail_all else set()
        elif key in avail:
            if key in open_flags:
                open_flags.discard(key)
            else:
                open_flags.add(key)
            detail_all = open_flags >= avail and bool(avail)

    toggle("stack")
    assert "stack" in open_flags or "stack" not in avail
    toggle("phase_plus")
    assert "phase_plus" in open_flags
    toggle("detail")
    assert detail_all is True
    assert open_flags >= avail
    toggle("detail")
    assert detail_all is False
    assert not open_flags


def test_preopen_why_and_auction_flags_pure():
    row = SimpleNamespace(
        ticker="BBRI",
        iep="4,820",
        delta_pct="+1.8",
        iev="12.4M",
        ncp="1.34",
        delta_iev="1.34",
        grade="A",
        risk="clear",
        evidence="ok",
        source=SimpleNamespace(
            trend_signal="BULLISH",
            opening_broker_backing_tag="BACKED",
            opening_broker_backing_score=0.9,
            opening_broker_buy_streak=3,
        ),
    )
    model = build_preopen_inspect_model(row, warnings=("w1",))
    keys = {f.key for f in model.flags}
    assert "why" in keys and "auction_plus" in keys
    by_key = {f.key: f for f in model.flags}
    assert by_key["why"].available is True
    assert by_key["auction_plus"].available is True or model.has_auction
    assert "BULLISH" in "\n".join(model.auction_lines)
    assert EXPANDABLE_FLAGS >= {"why", "auction_plus", "warn"}
    # Compact default: panels closed until chip (paint detail_open=False)
    assert model.has_auction is True
    assert model.has_warn is True


def test_judge_detail_chip_label_contract():
    """detail · d master chip label (what #jd-flag-detail shows)."""
    chip = FlagChip("detail", "detail · d", id="jd-flag-detail")
    chip.set_chip_state(available=True, expanded=False)
    assert chip.flag_key == "detail"
    assert "is-on" not in chip.classes
    chip.set_chip_state(available=True, expanded=True)
    assert "is-on" in chip.classes
