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


def test_flag_chip_height_auto_not_collapsed_by_border():
    """Uniform pills: height ≥1, labels visible, shared row baseline."""
    import asyncio

    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import Static

    class Host(App):
        CSS = """
        #row { height: 3; width: 100%; align: left middle; }
        """

        def compose(self) -> ComposeResult:
            with Horizontal(id="row"):
                yield Static("Detail", id="lab")
                yield FlagChip("detail", "detail · d", id="jd-flag-detail")
                yield FlagChip("stack", "stack", id="jd-flag-stack")
                yield FlagChip("readiness", "readiness", id="jd-flag-readiness")
                yield FlagChip("limited", "limited", id="jd-flag-limited")

    async def scenario() -> None:
        app = Host()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause(0.05)
            chips = [
                app.query_one("#jd-flag-detail", FlagChip),
                app.query_one("#jd-flag-stack", FlagChip),
                app.query_one("#jd-flag-readiness", FlagChip),
                app.query_one("#jd-flag-limited", FlagChip),
            ]
            ys = {c.region.y for c in chips}
            hs = {c.region.height for c in chips}
            assert len(ys) == 1, f"chips not on one baseline: {ys}"
            assert min(hs) >= 1
            for chip, label in zip(
                chips,
                ("detail · d", "stack", "readiness", "limited"),
                strict=True,
            ):
                assert label in str(chip.content)
                assert chip.size.height >= 1

    asyncio.run(scenario())


def test_verdict_action_and_gate_share_baseline():
    """Action + Gate badge aligned on one horizontal baseline."""
    import asyncio

    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import Static

    class Host(App):
        CSS = """
        #jd-verdict-row {
            height: 3;
            width: 100%;
            align: left middle;
        }
        .verdict-action {
            width: auto;
            height: 3;
            content-align: left middle;
            text-style: bold;
            color: #c97a72;
            padding: 0 2 0 0;
        }
        .verdict-gate {
            width: auto;
            height: 3;
            content-align: center middle;
            color: #c97a72;
            background: #1a1212;
            border: solid #3a2220;
            padding: 0 1;
        }
        """

        def compose(self) -> ComposeResult:
            with Horizontal(id="jd-verdict-row"):
                yield Static(" BLOCKED(struct) ", classes="verdict-action", id="jd-action")
                yield Static(" Gate BLOCKED ", classes="verdict-gate", id="jd-gate")

    async def scenario() -> None:
        app = Host()
        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause(0.05)
            action = app.query_one("#jd-action", Static)
            gate = app.query_one("#jd-gate", Static)
            assert action.region.y == gate.region.y
            assert action.region.height == gate.region.height

    asyncio.run(scenario())


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


def test_judge_detail_density_toggle_pure():
    """Judge density is brief ↔ detail only (CLI --detail dual), not multi-chips."""
    from src.adapters.tui.judge_flag_states import open_panels

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

    # brief: no detail sections open
    assert open_panels(model, detail_all=False, open_flags=set()) == set()
    # detail: all available sections
    assert open_panels(model, detail_all=True, open_flags=set()) == avail

    chip = FlagChip("detail", "detail · d", id="jd-flag-detail")
    chip.set_chip_state(available=True, expanded=False)
    assert "is-on" not in chip.classes
    chip.set_chip_state(available=True, expanded=True)
    assert "is-on" in chip.classes


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
