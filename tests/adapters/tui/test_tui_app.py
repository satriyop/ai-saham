"""Headless tests for the offline Daily Textual workspace."""

import asyncio

from textual.widgets import Input, Static

from src.adapters.tui.composition import create_tui_app
from src.adapters.tui.screens.candidate_browser_screen import CandidateBrowserScreen
from src.adapters.tui.screens.daily_screen import DailyScreen
from src.adapters.tui.screens.help import HelpScreen
from src.adapters.tui.screens.research_health_screen import ResearchHealthScreen
from src.adapters.tui.screens.ticker_research_screen import TickerResearchScreen

from .daily_fixtures import not_ready_response, ready_response
from .readiness_fixtures import (
    COHORT_A,
    COHORT_B,
    TARGET,
    empty_readiness_report,
    mixed_cohort_report,
    readiness_report,
)
from .research_fixtures import multi_result, single_result, ticker_response


class _RecordingCapability:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.response

    def fetch(self):
        raise AssertionError("provider fake must not be called")

    def save(self):
        raise AssertionError("write fake must not be called")


async def _wait_for_calls(pilot, capability, expected):
    for _ in range(30):
        await pilot.pause(0.01)
        if capability.calls == expected:
            await pilot.pause()
            return
    raise AssertionError(f"expected {expected} Daily calls, got {capability.calls}")


class _RecordingResearchHealthCapability:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, target, cohort):
        self.calls.append((target, cohort))
        return self.response

    def save(self):
        raise AssertionError("write fake must not be called")


async def _wait_for_research_calls(pilot, capability, expected):
    for _ in range(30):
        await pilot.pause(0.01)
        if len(capability.calls) == expected:
            await pilot.pause()
            return
    raise AssertionError(f"expected {expected} Research calls, got {len(capability.calls)}")


def test_launch_calls_daily_once_reload_once_and_navigation_does_not_call():
    async def scenario() -> None:
        capability = _RecordingCapability(ready_response())
        app = create_tui_app(daily_loader=capability)
        async with app.run_test(size=(100, 32)) as pilot:
            await _wait_for_calls(pilot, capability, 1)
            assert isinstance(app.screen, DailyScreen)
            assert app.screen.query_one("#daily-title", Static).content == "Daily"
            assert app.title == "AI Saham · Today"
            assert "OFFLINE · LQ45 · EOD 2026-07-21" == app.sub_title
            assert "authority READY" in str(app.screen.query_one("#daily-status", Static).content)
            assert "local warning" in str(app.screen.query_one("#daily-warnings", Static).content)

            await pilot.press("?", "tab", "right", "down")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            assert capability.calls == 1

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyScreen)
            assert capability.calls == 1

            await pilot.press("r")
            await _wait_for_calls(pilot, capability, 2)
            assert capability.calls == 2

    asyncio.run(scenario())


def test_shell_hierarchy_and_text_semantics_at_supported_sizes():
    async def scenario(size) -> None:
        capability = _RecordingCapability(not_ready_response())
        app = create_tui_app(daily_loader=capability)
        async with app.run_test(size=size) as pilot:
            await _wait_for_calls(pilot, capability, 1)
            status = app.screen.query_one("#daily-status", Static)
            assert "READY — authority NOT_READY" in str(status.content)
            assert "semantic-error" in status.classes
            assert "NOT_READY" in str(app.screen.query_one("#daily-readiness", Static).content)
            assert "local warning" in str(app.screen.query_one("#daily-warnings", Static).content)
            assert app.screen.query_one("Header")
            assert app.screen.query_one("Footer")

    asyncio.run(scenario((80, 24)))
    asyncio.run(scenario((120, 40)))


def test_reload_retains_last_good_content_while_recomputing():
    async def scenario() -> None:
        capability = _RecordingCapability(ready_response())
        app = create_tui_app(daily_loader=capability)
        async with app.run_test(size=(100, 32)) as pilot:
            await _wait_for_calls(pilot, capability, 1)
            previous = str(app.screen.query_one("#daily-warnings", Static).content)
            app.screen.action_reload()
            assert previous == str(app.screen.query_one("#daily-warnings", Static).content)
            await _wait_for_calls(pilot, capability, 2)

    asyncio.run(scenario())


def test_not_ready_is_ready_screen_output_without_usable_rankings():
    async def scenario() -> None:
        capability = _RecordingCapability(not_ready_response())
        app = create_tui_app(daily_loader=capability)
        async with app.run_test(size=(100, 32)) as pilot:
            await _wait_for_calls(pilot, capability, 1)
            assert "READY — authority NOT_READY" in str(
                app.screen.query_one("#daily-status", Static).content
            )
            assert "BBCA: flow" not in str(
                app.screen.query_one("#daily-accumulation", Static).content
            )

    asyncio.run(scenario())


def test_error_state_displays_exact_exception_class_and_message():
    def fail():
        raise ValueError("invalid local config")

    async def scenario() -> None:
        app = create_tui_app(daily_loader=fail)
        async with app.run_test(size=(100, 32)) as pilot:
            for _ in range(30):
                await pilot.pause(0.01)
                content = str(app.screen.query_one("#daily-warnings", Static).content)
                if "ValueError: invalid local config" in content:
                    break
            else:
                raise AssertionError("ERROR state was not rendered")

    asyncio.run(scenario())


def test_candidate_navigation_has_one_load_and_enter_runs_selected_ticker_once():
    async def scenario() -> None:
        accumulation_calls = []
        ticker_calls = []

        def load_accumulation(multi):
            accumulation_calls.append(multi)
            return multi_result() if multi else single_result()

        def load_ticker(ticker):
            ticker_calls.append(ticker)
            return ticker_response()

        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            accumulation_loader=load_accumulation,
            ticker_loader=load_ticker,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("2")
            for _ in range(30):
                await pilot.pause(0.01)
                if accumulation_calls == [False]:
                    break
            assert isinstance(app.screen, CandidateBrowserScreen)
            assert accumulation_calls == [False]

            await pilot.press("j", "k", "down", "up")
            await pilot.pause()
            assert accumulation_calls == [False]
            assert ticker_calls == []

            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause(0.01)
                if ticker_calls:
                    break
            assert isinstance(app.screen, TickerResearchScreen)
            assert ticker_calls == ["BBRI"]
            canonical = str(app.screen.query_one("#ticker-canonical", Static).content)
            preview = str(app.screen.query_one("#ticker-preview", Static).content)
            assert "CANONICAL_ONLY" in canonical
            assert "PREVIEW_ONLY" not in canonical
            assert "NON-CANONICAL PREVIEW" in preview
            assert "PREVIEW_ONLY" in preview

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, CandidateBrowserScreen)
            assert accumulation_calls == [False]

            await pilot.press("m")
            for _ in range(30):
                await pilot.pause(0.01)
                if accumulation_calls == [False, True]:
                    break
            assert accumulation_calls == [False, True]

    asyncio.run(scenario())


def test_candidate_compact_mode_keeps_canonical_action_risk_and_data_text():
    async def scenario() -> None:
        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            accumulation_loader=lambda multi: single_result(),
            ticker_loader=lambda ticker: ticker_response(ticker=ticker),
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("2")
            for _ in range(30):
                await pilot.pause(0.01)
                if isinstance(app.screen, CandidateBrowserScreen):
                    content = str(app.screen.query_one("#candidate-list").render())
                    if "BBRI" in content:
                        break
            assert app.screen.has_class("compact")
            selected = str(app.screen.query_one("#candidate-selected", Static).content)
            assert "Action: WATCH" in selected
            assert "Risk: OPEN" in selected
            assert "Data: ALIGNED" in selected

    asyncio.run(scenario())


def test_research_is_idle_until_explicit_submit_and_renders_exact_report():
    async def scenario() -> None:
        capability = _RecordingResearchHealthCapability(readiness_report())
        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            research_health_loader=capability,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("3")
            await pilot.pause()
            assert isinstance(app.screen, ResearchHealthScreen)
            assert app.title == "AI Saham · Research"
            assert capability.calls == []
            assert "IDLE" in str(app.screen.query_one("#research-health-status", Static).content)
            assert (
                str(app.screen.query_one("#research-health-banner", Static).content)
                == "DIAGNOSTIC ONLY — NOT PROMOTION EVIDENCE"
            )

            await pilot.press("tab", "shift+tab", "right", "left")
            await pilot.pause()
            assert capability.calls == []

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert capability.calls == []
            assert "ERROR — ValueError: target must not be blank" == str(
                app.screen.query_one("#research-health-status", Static).content
            )

            app.screen.query_one("#research-target", Input).value = f" {TARGET} "
            app.screen.query_one("#research-cohort", Input).value = f" {COHORT_A} "
            app.screen.query_one("#research-target", Input).focus()
            await pilot.press("enter")
            await _wait_for_research_calls(pilot, capability, 1)
            assert capability.calls == [(f" {TARGET} ", f" {COHORT_A} ")]
            assert "READY — report loaded" == str(
                app.screen.query_one("#research-health-status", Static).content
            )
            eligibility = str(app.screen.query_one("#research-eligibility", Static).content)
            assert "Split: EPHEMERAL_CHRONOLOGICAL_70_30" in eligibility
            assert "Diagnostic ready: YES" in eligibility
            assert "Patch eligible: YES" in eligibility
            assert "Promotion eligible: NO" in eligibility
            blockers = str(app.screen.query_one("#research-blockers", Static).content)
            assert "calibration blocker" in blockers
            exclusions = str(app.screen.query_one("#research-exclusions", Static).content)
            for name in readiness_report().exclusions.to_dict():
                assert name in exclusions

    asyncio.run(scenario())


def test_research_mixed_cohort_is_visible_and_never_pooled():
    async def scenario() -> None:
        capability = _RecordingResearchHealthCapability(mixed_cohort_report())
        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            research_health_loader=capability,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("3")
            await pilot.pause()
            app.screen.query_one("#research-target", Input).value = TARGET
            await pilot.press("enter")
            await _wait_for_research_calls(pilot, capability, 1)
            cohorts = str(app.screen.query_one("#research-cohorts", Static).content)
            eligibility = str(app.screen.query_one("#research-eligibility", Static).content)
            blockers = str(app.screen.query_one("#research-blockers", Static).content)
            assert "Selected: —" in cohorts
            assert COHORT_A in cohorts
            assert COHORT_B in cohorts
            assert "IS / OOS: 0 / 0" in eligibility
            assert "OOS profit factor: —" in eligibility
            assert "OOS average return: —" in eligibility
            assert "mixed_semantic_cohorts" in blockers

    asyncio.run(scenario())


def test_empty_research_report_keeps_other_routes_available():
    async def scenario() -> None:
        capability = _RecordingResearchHealthCapability(empty_readiness_report())
        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            research_health_loader=capability,
        )
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("3")
            await pilot.pause()
            app.screen.query_one("#research-target", Input).value = TARGET
            await pilot.press("enter")
            await _wait_for_research_calls(pilot, capability, 1)
            assert "EMPTY — report loaded" == str(
                app.screen.query_one("#research-health-status", Static).content
            )
            assert "no forward labels generated yet" in str(
                app.screen.query_one("#research-blockers", Static).content
            )
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyScreen)

    asyncio.run(scenario())
