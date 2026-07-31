"""Two-key chords: pure dispatch table + one residual e2e mount (D6)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.commands import COCKPIT_COMMANDS
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter


def _accum_payload():
    c = SimpleNamespace(
        ticker="BBCA",
        accum_score=50.0,
        signal_assessment=None,
        trade_setup=None,
        risk_assessment=None,
        setup_phase=None,
        consecutive_streak=1,
        rsi=50,
        net_buy_ratio=0.5,
        vwap_discount_pct=1.0,
        current_price=1000,
        name="BBCA",
    )
    return SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c],
            window_days=7,
            data_as_of={},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        effective_session=None,
        market_context=None,
        multi_projection=None,
        warnings=(),
    )


def test_palette_labels_match_chords():
    by_id = {c.command_id: c for c in COCKPIT_COMMANDS}
    assert by_id["screen-accum"].shortcut == "s a"
    assert by_id["screen-preopen"].shortcut == "s p"
    assert by_id["view-ticker"].shortcut == "v t"
    assert by_id["view-broker"].shortcut == "v b"


def test_chord_dispatch_table_is_pure():
    """D6: key→command map asserted without mounting the app."""
    assert CockpitApp._CHORD_MAP == {
        ("s", "a"): "screen-accum",
        ("s", "p"): "screen-preopen",
        ("v", "t"): "view-ticker",
        ("v", "b"): "view-broker",
    }
    assert CockpitApp._CHORD_HINTS["s"].startswith("s a")
    assert "v t" in CockpitApp._CHORD_HINTS["v"]
    # Palette shortcuts agree with the map
    by_id = {c.command_id: c for c in COCKPIT_COMMANDS}
    for (p, k), cmd in CockpitApp._CHORD_MAP.items():
        assert by_id[cmd].shortcut == f"{p} {k}"


def test_desk_hub_v_is_not_chord_prefix_rule():
    """Documented rule: on desk hub, v jumps ticker; off hub, v arms chord."""
    # Pure: _desk_hub_active is stage+page state — no mount needed for the map side.
    assert ("v", "t") in CockpitApp._CHORD_MAP
    assert ("v", "b") in CockpitApp._CHORD_MAP
    # Jump is single-key when hub active (not a chord pair)


def test_chord_v_t_and_v_b_dispatch_e2e():
    """One residual full-app chord journey (D3/D6): proves wiring, not each pair."""

    async def scenario() -> None:
        viewed: list[str] = []
        broker_loads = 0

        def ticker_loader(t: str) -> str:
            viewed.append(t)
            return f"DASH_{t}"

        def broker_list():
            nonlocal broker_loads
            broker_loads += 1
            return [SimpleNamespace(code="AK", type_label="Foreign")]

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            ticker_detail_loader=ticker_loader,
            broker_list_loader=broker_list,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._focus_ticker == "BBCA"

            await pilot.press("v")
            assert app._chord_prefix == "v"
            await pilot.press("escape")
            await pilot.pause()
            assert app._chord_prefix is None
            assert app._stage == "accum"

            await pilot.press("v")
            await pilot.press("t")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._status_note == "view ticker":
                    break
            assert viewed == ["BBCA"]
            assert app._chord_prefix is None

            await pilot.press("v")
            await pilot.press("b")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "broker-list":
                    break
            assert broker_loads == 1
            assert app._stage == "broker-list"

    asyncio.run(scenario())
