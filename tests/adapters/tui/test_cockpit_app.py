"""Cockpit shell + palette + empty (Phases 0–1)."""

from __future__ import annotations

import asyncio

from src.adapters.tui.commands import filter_commands
from src.adapters.tui.composition import create_cockpit_app, create_tui_app
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.screens.help import HelpModal
from src.adapters.tui.screens.palette import CommandPalette


def test_create_tui_app_returns_cockpit():
    app = create_tui_app()
    assert isinstance(app, CockpitApp)
    assert create_cockpit_app is create_tui_app


def test_filter_commands_matches_accum():
    hits = filter_commands("accum")
    assert any(c.command_id == "screen-accum" for c in hits)
    assert not any(c.command_id == "fetch" for c in hits)


def test_filter_commands_empty_returns_all():
    assert len(filter_commands("")) >= 8


def test_cockpit_mounts_layout_b_and_opens_palette():
    async def scenario() -> None:
        # No loaders → stays shell (unit isolation). Real app auto-loads accum.
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            assert app.query_one("#main")
            assert app.query_one("#sidebar")
            assert app.query_one("#status")
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, CommandPalette)

    asyncio.run(scenario())


def test_view_broker_list_enter_show_and_esc():
    """Ctrl+P View broker: list desks → Enter show → esc list → esc board."""

    async def scenario() -> None:
        from types import SimpleNamespace

        from src.adapters.tui.controllers.board_controller import BoardController
        from src.adapters.tui.presenters.accum_presenter import AccumPresenter

        def make_accum():
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

        desks = [
            SimpleNamespace(
                code="AK",
                type_label="Foreign",
                as_of="2026-07-28",
                day_net="1.20B",
                net5="3.80B",
                streak="4",
                delta1="+0.20B",
                tickers="12",
                top_buy="BBCA",
                has_data=True,
            ),
            SimpleNamespace(
                code="YP",
                type_label="Local",
                as_of="—",
                day_net="—",
                net5="—",
                streak="—",
                delta1="—",
                tickers="—",
                top_buy="—",
                has_data=False,
            ),
        ]
        shown: list[str] = []

        def show_loader(code: str):
            shown.append(code)
            return SimpleNamespace(text=f"DESK_SHOW_{code}\nDay net 1.0B", jump_ticker="BBCA")

        app = CockpitApp(
            accum_loader=make_accum,
            accum_controller=BoardController(make_accum),
            accum_presenter=AccumPresenter(),
            broker_list_loader=lambda: desks,
            broker_show_loader=show_loader,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._run_command("view-broker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "broker-list":
                    break
            assert app._stage == "broker-list"
            assert len(app._broker_rows) == 2
            assert app._broker_list_return == "accum"
            # Enriched radar columns present on row model
            assert app._broker_rows[0].day_net == "1.20B"
            assert app._broker_rows[0].net5 == "3.80B"
            assert app._broker_rows[0].streak == "4"
            assert app._broker_rows[0].top_buy == "BBCA"
            app._open_broker_desk_show()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and shown:
                    break
            assert shown == ["AK"]
            assert "View · broker show · AK" in app._board_title
            assert "DESK_SHOW_AK" in app._detail_text
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "broker-list"
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

    asyncio.run(scenario())


def test_palette_view_ticker_is_dashboard_not_board_inspect():
    """Ctrl+P View ticker = cache dashboard; Enter still does engine inspect."""

    async def scenario() -> None:
        from types import SimpleNamespace

        from src.adapters.tui.controllers.board_controller import BoardController
        from src.adapters.tui.presenters.accum_presenter import AccumPresenter

        def make_accum():
            c = SimpleNamespace(
                ticker="BBCA",
                accum_score=50.0,
                signal_assessment=SimpleNamespace(
                    assessment=SimpleNamespace(
                        score=72,
                        strength=SimpleNamespace(value="STRONG"),
                    )
                ),
                trade_setup=SimpleNamespace(
                    action=SimpleNamespace(value="WATCH", short="WATCH"),
                    rationale="x",
                ),
                risk_assessment=SimpleNamespace(gate_triggered=None, rationale=()),
                setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
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

        viewed: list[str] = []

        def fake_view(ticker: str) -> str:
            viewed.append(ticker)
            return f"DASHBOARD_FOR_{ticker}\nidentity panel stub"

        app = CockpitApp(
            accum_loader=make_accum,
            accum_controller=BoardController(make_accum),
            accum_presenter=AccumPresenter(),
            ticker_detail_loader=fake_view,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            # Palette command → CLI view ticker path
            app._run_command("view-ticker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and viewed:
                    break
            assert viewed == ["BBCA"]
            assert "View · ticker desk · BBCA" in app._board_title
            assert app._status_note == "view ticker"
            assert app._ticker_desk_model is not None
            assert app._ticker_desk_model.ticker == "BBCA"
            # String loader body preserved on model; primary detail_text is desk hierarchy
            assert "DASHBOARD_FOR_BBCA" in (app._ticker_desk_model.body or "")
            assert (
                "LAST · LOCAL CLOSE" in app._detail_text or "View · ticker desk" in app._detail_text
            )
            assert "HARGA MAST" not in app._detail_text
            # Board Enter → judge, not dashboard
            await pilot.press("escape")
            await pilot.pause()
            app.query_one("#board-table").focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert app._stage == "detail"
            assert "Judge" in app._board_title
            assert app._status_note == "judge"

    asyncio.run(scenario())


def test_board_enter_opens_accum_inspect():
    """Enter on focused DataTable must open inspect (not be swallowed as no-op)."""

    async def scenario() -> None:
        from types import SimpleNamespace

        from src.adapters.tui.controllers.board_controller import BoardController
        from src.adapters.tui.presenters.accum_presenter import AccumPresenter

        def make_accum():
            c = SimpleNamespace(
                ticker="BBCA",
                accum_score=50.0,
                signal_assessment=SimpleNamespace(
                    assessment=SimpleNamespace(
                        score=72,
                        strength=SimpleNamespace(value="STRONG"),
                    )
                ),
                trade_setup=SimpleNamespace(
                    action=SimpleNamespace(value="WATCH", short="WATCH"),
                    rationale="x",
                ),
                risk_assessment=SimpleNamespace(gate_triggered=None, rationale=()),
                setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
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

        app = CockpitApp(
            accum_loader=make_accum,
            accum_controller=BoardController(make_accum),
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            app.query_one("#board-table").focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert app._stage == "detail"
            assert "Screen · accum ·" in app._board_title or "BBCA" in app._board_title

    asyncio.run(scenario())


def test_palette_enter_runs_preopen_not_view_ticker():
    """Regression: app Enter must not steal palette run (priority/Input bug)."""

    async def scenario() -> None:
        from decimal import Decimal
        from types import SimpleNamespace

        from src.adapters.tui.controllers.board_controller import BoardController
        from src.adapters.tui.presenters.accum_presenter import AccumPresenter
        from src.adapters.tui.presenters.preopen_presenter import PreOpenPresenter

        def make_accum():
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

        def make_preopen():
            c = SimpleNamespace(
                ticker="BBRI",
                iep=1000,
                iep_gap_pct=Decimal("1.0"),
                gap_pct=Decimal("1.0"),
                iev=1_000_000,
                iev_intensity=1.2,
                opening_broker_backing_tag="BACKED",
                trend_signal="BULLISH",
            )
            return SimpleNamespace(
                response=SimpleNamespace(
                    result=SimpleNamespace(candidates=[c]),
                    warnings=[],
                ),
                snapshot_date="2026-07-25",
                warnings=(),
            )

        app = CockpitApp(
            accum_loader=make_accum,
            accum_controller=BoardController(make_accum),
            accum_presenter=AccumPresenter(),
            preopen_loader=make_preopen,
            preopen_controller=BoardController(make_preopen, empty_when=lambda _p: False),
            preopen_presenter=PreOpenPresenter(),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            # Search focuses Input; Enter must run filtered command, not view-ticker.
            for ch in "pre":
                await pilot.press(ch)
            await pilot.pause()
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "preopen" and app._rows:
                    break
            assert not isinstance(app.screen, CommandPalette)
            assert app._stage == "preopen"
            assert app._board_kind == "preopen"
            assert app._rows
            assert app._rows[0].ticker == "BBRI"

    asyncio.run(scenario())


def test_mount_with_loader_auto_starts_accum():
    async def scenario() -> None:
        from types import SimpleNamespace

        from src.adapters.tui.controllers.board_controller import BoardController
        from src.adapters.tui.presenters.accum_presenter import AccumPresenter

        cand = SimpleNamespace(
            ticker="BBRI",
            accum_score=80.0,
            rsi=50.0,
            consecutive_streak=3,
            net_buy_ratio=0.75,
            vwap_discount_pct=2.0,
            current_price=5000,
            setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
            trade_setup=SimpleNamespace(
                action=SimpleNamespace(value="WATCH", short="WATCH"),
                rationale="test",
            ),
            signal_assessment=SimpleNamespace(
                assessment=SimpleNamespace(score=72, strength=SimpleNamespace(value="STRONG"))
            ),
            risk_assessment=SimpleNamespace(gate_triggered=None, rationale=()),
            name="BBRI",
        )
        projection = SimpleNamespace(
            candidates=[cand],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-25"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        )
        result = SimpleNamespace(single_projection=projection, multi_projection=None, warnings=())
        loader = lambda: result  # noqa: E731
        app = CockpitApp(
            accum_loader=loader,
            accum_controller=BoardController(loader),
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and len(app._rows) == 1:
                    break
            assert app._stage == "accum"
            assert app._rows[0].ticker == "BBRI"

    asyncio.run(scenario())


def test_empty_cache_command_switches_stage():
    from src.adapters.tui.local_cache_health import assess_local_cache_health

    # True-empty cache health so poster title is "No local market data"
    # (unknown/default health paints "Cache health unclear").
    health = assess_local_cache_health(universe="lq45", candle_latest=None, broker_latest=None)

    async def scenario() -> None:
        app = CockpitApp(cache_health_loader=lambda: health)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._run_command("empty-demo")
            await pilot.pause()
            assert app._stage == "empty"
            # Empty stage paints HealthPosterDesk (stage-body hidden).
            title = str(app.query_one("#hp-title").content)
            assert "No local market data" in title

    asyncio.run(scenario())


def test_toggle_sidebar_and_help():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert app._sidebar_visible is False
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpModal)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(scenario())


def test_plan_blocked_when_empty():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._run_command("empty-demo")
            await pilot.pause()
            app._run_command("plan-swing")
            await pilot.pause()
            # Still empty — plan stage must not open without focus
            assert app._stage == "empty"
            assert app._stage != "plan"

    asyncio.run(scenario())


def test_supported_terminal_sizes_mount():
    """Phase 5: 80x24 navigable shell; 120x40 reference layout."""

    async def scenario(size: tuple[int, int]) -> None:
        app = CockpitApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one("#main")
            assert app.query_one("#status")
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(scenario((80, 24)))
    asyncio.run(scenario((120, 40)))
