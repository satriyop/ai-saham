from __future__ import annotations

from src.adapters.tui.controllers.research_health_controller import (
    ResearchHealthController,
)
from src.adapters.tui.presenters.research_health_presenter import (
    ResearchHealthPresenter,
)
from src.adapters.tui.state import ScreenStatus
from src.application.use_case.report_signal_readiness_use_case import (
    ReportSignalReadinessRequest,
    ReportSignalReadinessUseCase,
)

from .readiness_fixtures import (
    COHORT_A,
    TARGET,
    empty_readiness_report,
    mixed_cohort_report,
    readiness_report,
)


def _dispatch(callback, *args):
    callback(*args)


def test_blank_target_is_exact_error_with_zero_calls():
    calls = []
    controller = ResearchHealthController(lambda target, cohort: calls.append(target))
    generation = controller.begin()
    controller.execute_generation(
        generation,
        target="   ",
        cohort=None,
        dispatch=_dispatch,
        listener=lambda state: None,
    )
    assert calls == []
    assert controller.state.status is ScreenStatus.ERROR
    assert controller.state.error_type == "ValueError"
    assert controller.state.error_message == "target must not be blank"


def test_one_submission_preserves_target_and_cohort_exactly():
    calls = []
    report = readiness_report()

    def load(target, cohort):
        calls.append((target, cohort))
        return report

    controller = ResearchHealthController(load)
    generation = controller.begin()
    controller.execute_generation(
        generation,
        target=f" {TARGET} ",
        cohort=f" {COHORT_A} ",
        dispatch=_dispatch,
        listener=lambda state: None,
    )
    assert calls == [(f" {TARGET} ", f" {COHORT_A} ")]
    assert controller.state.payload is report
    assert controller.state.status is ScreenStatus.READY


def test_malformed_target_preserves_exact_use_case_error():
    calls = []

    def load(target, cohort):
        calls.append((target, cohort))
        raise ValueError("target must end with one of: SWING_10D, SWING_20D")

    controller = ResearchHealthController(load)
    generation = controller.begin()
    controller.execute_generation(
        generation,
        target="malformed",
        cohort=None,
        dispatch=_dispatch,
        listener=lambda state: None,
    )
    assert calls == [("malformed", None)]
    assert controller.state.status is ScreenStatus.ERROR
    assert controller.state.error_type == "ValueError"
    assert controller.state.error_message == "target must end with one of: SWING_10D, SWING_20D"


def test_empty_report_is_valid_empty_and_mixed_cohort_is_ready_blocked():
    controller = ResearchHealthController(lambda target, cohort: empty_readiness_report())
    generation = controller.begin()
    controller.execute_generation(
        generation,
        target=TARGET,
        cohort=None,
        dispatch=_dispatch,
        listener=lambda state: None,
    )
    assert controller.state.status is ScreenStatus.EMPTY

    controller = ResearchHealthController(lambda target, cohort: mixed_cohort_report())
    generation = controller.begin()
    controller.execute_generation(
        generation,
        target=TARGET,
        cohort=None,
        dispatch=_dispatch,
        listener=lambda state: None,
    )
    assert controller.state.status is ScreenStatus.READY
    assert controller.state.payload.blockers == ("mixed_semantic_cohorts",)


def test_presenter_preserves_source_all_exclusions_blockers_and_authorities():
    report = readiness_report()
    view = ResearchHealthPresenter().present(report)
    assert view.source is report
    assert dict(view.exclusions) == report.exclusions.to_dict()
    assert view.blockers == report.blockers
    assert view.notes == report.notes
    assert view.eligibility.diagnostic_ready is True
    assert view.eligibility.patch_eligible is True
    assert view.eligibility.promotion_eligible is False


def test_presenter_never_pools_unresolved_cohorts():
    report = mixed_cohort_report()
    view = ResearchHealthPresenter().present(report)
    assert view.selected_cohort is None
    assert view.available_cohorts == report.available_semantic_compatibility_ids
    assert view.eligibility.is_count == 0
    assert view.eligibility.oos_count == 0
    assert view.blockers == ("mixed_semantic_cohorts",)


def test_stale_report_cannot_replace_newer_submission():
    reports = iter((readiness_report(), mixed_cohort_report()))
    queued = []
    controller = ResearchHealthController(lambda target, cohort: next(reports))
    first = controller.begin()
    controller.execute_generation(
        first,
        target=TARGET,
        cohort=None,
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )
    second = controller.begin()
    controller.execute_generation(
        second,
        target=TARGET,
        cohort=COHORT_A,
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )
    queued[1][0](*queued[1][1])
    newer = controller.state.payload
    queued[0][0](*queued[0][1])
    assert controller.state.generation == second
    assert controller.state.payload is newer


def test_real_readiness_use_case_never_calls_write_methods():
    class Observations:
        def list_canonical_snapshot_dates(self):
            return []

        def save_many(self, rows):
            raise AssertionError("observation write forbidden")

    class Labels:
        def list(self, **kwargs):
            return []

        def save_many(self, rows):
            raise AssertionError("label write forbidden")

    use_case = ReportSignalReadinessUseCase(
        candidate_observations_repository=Observations(),
        signal_forward_labels_repository=Labels(),
    )
    controller = ResearchHealthController(
        lambda target, cohort: use_case.execute(ReportSignalReadinessRequest(target, cohort))
    )
    generation = controller.begin()
    controller.execute_generation(
        generation,
        target=TARGET,
        cohort=None,
        dispatch=_dispatch,
        listener=lambda state: None,
    )
    assert controller.state.status is ScreenStatus.EMPTY
