from dataclasses import replace

from src.adapters.tui.presenters.daily_presenter import DailyPresenter

from .daily_fixtures import empty_response, not_ready_response, partial_response, ready_response


def test_presenter_preserves_source_clocks_authority_and_warnings():
    response = partial_response()
    view = DailyPresenter().present(response)

    assert view.source is response
    assert [clock.label for clock in view.clocks] == [
        "Live session",
        "Latest completed EOD",
        "Opening snapshot",
    ]
    assert [clock.value for clock in view.clocks] == [
        "2026-07-22",
        "2026-07-21",
        "2026-07-22",
    ]
    assert view.overall_authority == "PARTIAL"
    assert view.readiness[0].status == "PARTIAL"
    assert view.warnings == ("local warning",)
    assert view.setup_lens_warnings == ("setup warning",)


def test_not_ready_suppresses_rankings_even_if_input_is_contradictory():
    view = DailyPresenter().present(not_ready_response())

    assert view.overall_authority == "NOT_READY"
    assert view.accumulation_candidates == ()
    assert view.setup_lens_rows == ()


def test_empty_does_not_fabricate_regime_or_candidates():
    view = DailyPresenter().present(empty_response())
    assert view.regime is None
    assert view.opening_candidates == ()
    assert view.accumulation_candidates == ()
    assert view.setup_lens_rows == ()


def test_presenter_copies_unknown_application_action_without_interpreting_it():
    response = ready_response()
    custom = replace(
        response.daily_accumulation_candidates[0],
        action="FUTURE_ACTION",
        risk_status="FUTURE_STATUS",
    )
    view = DailyPresenter().present(replace(response, daily_accumulation_candidates=[custom]))
    assert view.accumulation_candidates[0].action == "FUTURE_ACTION"
    assert view.accumulation_candidates[0].risk_status == "FUTURE_STATUS"
