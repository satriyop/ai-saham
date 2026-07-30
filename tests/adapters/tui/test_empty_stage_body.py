"""Honest empty-stage body: true empty cache vs 0 candidates vs ready health."""

from __future__ import annotations

import asyncio
from datetime import date

from src.adapters.tui.empty_stage_body import format_empty_stage_body
from src.adapters.tui.local_cache_health import assess_local_cache_health
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.state import ScreenState, ScreenStatus


def test_true_empty_cache_copy():
    text = format_empty_stage_body(
        cache_status="empty",
        board_title="Screen · —",
        meta="waiting on local data",
        board_kind="none",
    )
    assert "No local market data" in text
    assert "cannot invent" in text.lower() or "refuses to invent" in text.lower()


def test_zero_candidates_with_ready_cache_does_not_claim_no_data():
    text = format_empty_stage_body(
        cache_status="ready",
        board_title="Screen · accumulation",
        meta="local · 0 candidates",
        board_kind="accum",
    )
    assert "No local market data" not in text
    assert "0" in text.lower() or "candidate" in text.lower()
    assert "local cache" in text.lower() or "local data" in text.lower()


def test_preopen_empty_is_iep_specific():
    text = format_empty_stage_body(
        cache_status="ready",
        board_title="Screen · pre-open",
        meta="no IEP / empty local",
        board_kind="preopen",
    )
    assert "No local market data" not in text
    assert "IEP" in text or "pre-open" in text.lower() or "IEV" in text


def test_ready_health_generic_empty_not_no_market_data():
    text = format_empty_stage_body(
        cache_status="ready",
        board_title="Screen · —",
        meta="local cache · no board rows",
        board_kind="none",
    )
    assert "No local market data" not in text
    assert (
        "local cache present" in text.lower()
        or "nothing to list" in text.lower()
        or "local cache ready" in text.lower()
        or "poster · ready" in text.lower()
    )


def test_lag_health_uses_lag_poster():
    text = format_empty_stage_body(
        cache_status="lag",
        board_title="Screen · —",
        meta="waiting",
        board_kind="none",
    )
    assert "No local market data" not in text
    assert "lag" in text.lower()
    assert "poster" in text.lower() or "lagging" in text.lower()


def test_cockpit_empty_demo_true_empty_still_says_no_market_data():
    health = assess_local_cache_health(universe="lq45", candle_latest=None, broker_latest=None)

    async def scenario() -> None:
        app = CockpitApp(cache_health_loader=lambda: health)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._run_command("empty-demo")
            await pilot.pause(0.05)
            assert app._stage == "empty"
            stage_text = str(app.query_one("#stage-body").render())
            assert "No local market data" in stage_text

    asyncio.run(scenario())


def test_cockpit_zero_candidate_empty_body_honest_with_ready_health():
    health = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 28),
    )

    async def scenario() -> None:
        app = CockpitApp(cache_health_loader=lambda: health)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._on_accum_state(
                ScreenState(
                    generation=1,
                    status=ScreenStatus.EMPTY,
                    payload=None,
                )
            )
            await pilot.pause(0.05)
            assert app._stage == "empty"
            stage_text = str(app.query_one("#stage-body").render())
            assert "No local market data" not in stage_text
            assert "candidate" in stage_text.lower() or "0" in stage_text
            # Cache rail still ready
            cache_text = str(app.query_one("#side-cache").render())
            assert "2026-07-28" in cache_text

    asyncio.run(scenario())


def test_cockpit_show_empty_with_ready_health_not_no_market_data():
    health = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 27),
    )

    async def scenario() -> None:
        app = CockpitApp(cache_health_loader=lambda: health)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._show_empty()
            await pilot.pause(0.05)
            stage_text = str(app.query_one("#stage-body").render())
            assert "No local market data" not in stage_text
            assert "local" in stage_text.lower()

    asyncio.run(scenario())
