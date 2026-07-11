"""Tests for AssessCorporateActionEventRiskUseCase.

Deterministic, config-driven event-risk context over the market-wide
corporate action calendar. Context/diagnostics only — must never touch
SignalEngine, RiskEngine, or TradeSetup (verified via source inspection
below).

Layer: Application.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from src.application.use_case.assess_corporate_action_event_risk_use_case import (
    AssessCorporateActionEventRiskRequest,
    AssessCorporateActionEventRiskUseCase,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskFlag,
    CorporateActionEventRiskSeverity,
)
from src.infrastructure.config.corporate_action_policy_config import (
    load_corporate_action_policy_config,
)

SRC_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "application"
    / "use_case"
    / "assess_corporate_action_event_risk_use_case.py"
)


class FakeCorporateActionCalendarRepository:
    """Minimal fake implementing only get_events_for_ticker, per the use case's
    actual dependency surface (no other repository method is called)."""

    def __init__(self, events: list[CorporateActionCalendarEvent]) -> None:
        self._events = events
        self.calls: list[tuple[str, date, date]] = []

    def get_events_for_ticker(self, ticker, from_date, to_date, event_types=None):
        self.calls.append((ticker, from_date, to_date))
        return self._events


def _default_policy():
    return load_corporate_action_policy_config()


def _dividend_event(
    ex_date: date, *, source_event_id: str = "div-1", note: str | None = None
) -> CorporateActionCalendarEvent:
    return CorporateActionCalendarEvent(
        event_type=CorporateActionType.DIVIDEND,
        source_event_id=source_event_id,
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.EX_DATE, event_date=ex_date
            ),
        ),
        event_note=note,
    )


def test_no_matching_events_returns_none_severity_and_empty_events():
    repo = FakeCorporateActionCalendarRepository([])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=date(2026, 7, 13))
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.NONE
    assert assessment.events == ()
    assert assessment.nearest_event_date is None
    assert "no" in assessment.rationale.lower() or "No" in assessment.rationale


def test_dividend_ex_date_within_window_yields_warning_and_price_distortion_flag():
    as_of = date(2026, 7, 13)
    ex_date = date(2026, 7, 15)  # +2 days, within default lookahead_days=5
    repo = FakeCorporateActionCalendarRepository([_dividend_event(ex_date)])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.WARNING
    assert len(assessment.events) == 1
    event = assessment.events[0]
    assert event.event_type == "dividend"
    assert event.date_role == "ex_date"
    assert event.event_date == ex_date
    assert event.days_from_as_of == 2
    assert CorporateActionEventRiskFlag.PRICE_DISTORTION in event.flags
    assert assessment.nearest_event_date == ex_date


def test_dividend_payment_date_not_configured_does_not_match():
    as_of = date(2026, 7, 13)
    payment_date = date(2026, 7, 15)
    event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.DIVIDEND,
        source_event_id="div-2",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.PAYMENT_DATE, event_date=payment_date
            ),
        ),
    )
    repo = FakeCorporateActionCalendarRepository([event])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.NONE
    assert assessment.events == ()


def test_rights_issue_ex_date_within_window_yields_warning_with_two_flags():
    as_of = date(2026, 7, 13)
    ex_date = date(2026, 7, 18)  # +5 days, within lookahead_days=10
    event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.RIGHTS_ISSUE,
        source_event_id="ri-1",
        ticker="ANTM",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.EX_DATE, event_date=ex_date
            ),
        ),
    )
    repo = FakeCorporateActionCalendarRepository([event])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="ANTM", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.WARNING
    assert len(assessment.events) == 1
    flags = assessment.events[0].flags
    assert CorporateActionEventRiskFlag.PRICE_DISTORTION in flags
    assert CorporateActionEventRiskFlag.LIQUIDITY_DISTORTION in flags


def test_rups_rups_date_within_window_yields_info_severity_only():
    as_of = date(2026, 7, 13)
    rups_date = date(2026, 7, 17)  # +4 days, within lookahead_days=7
    event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.RUPS,
        source_event_id="rups-1",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.RUPS_DATE, event_date=rups_date
            ),
        ),
    )
    repo = FakeCorporateActionCalendarRepository([event])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.INFO
    assert len(assessment.events) == 1
    assert CorporateActionEventRiskFlag.GOVERNANCE_CONTEXT in assessment.events[0].flags


def test_pubex_pubex_date_within_window_yields_info_severity_only():
    as_of = date(2026, 7, 13)
    pubex_date = date(2026, 7, 16)  # +3 days, within lookahead_days=7
    event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.PUBEX,
        source_event_id="pubex-1",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.PUBEX_DATE, event_date=pubex_date
            ),
        ),
    )
    repo = FakeCorporateActionCalendarRepository([event])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.INFO
    assert CorporateActionEventRiskFlag.DISCLOSURE_CONTEXT in assessment.events[0].flags


def test_tender_offer_offer_start_within_window_yields_warning_special_situation():
    as_of = date(2026, 7, 13)
    offer_start = date(2026, 7, 20)  # +7 days, within lookahead_days=10
    event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.TENDER_OFFER,
        source_event_id="to-1",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.OFFER_START, event_date=offer_start
            ),
        ),
    )
    repo = FakeCorporateActionCalendarRepository([event])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.WARNING
    assert CorporateActionEventRiskFlag.SPECIAL_SITUATION in assessment.events[0].flags


def test_tender_offer_offer_end_within_window_yields_warning_special_situation():
    as_of = date(2026, 7, 13)
    offer_end = date(2026, 7, 21)  # +8 days, within lookahead_days=10
    event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.TENDER_OFFER,
        source_event_id="to-2",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.OFFER_END, event_date=offer_end
            ),
        ),
    )
    repo = FakeCorporateActionCalendarRepository([event])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.WARNING
    assert CorporateActionEventRiskFlag.SPECIAL_SITUATION in assessment.events[0].flags


def test_event_before_lookback_window_is_excluded():
    as_of = date(2026, 7, 13)
    ex_date = as_of - timedelta(days=10)  # dividend ex_date lookback_days=2
    repo = FakeCorporateActionCalendarRepository([_dividend_event(ex_date)])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.NONE
    assert assessment.events == ()


def test_event_after_lookahead_window_is_excluded():
    as_of = date(2026, 7, 13)
    ex_date = as_of + timedelta(days=20)  # dividend ex_date lookahead_days=5
    repo = FakeCorporateActionCalendarRepository([_dividend_event(ex_date)])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    assessment = response.assessment

    assert assessment.severity == CorporateActionEventRiskSeverity.NONE
    assert assessment.events == ()


def test_sorting_is_deterministic_by_full_tuple_key():
    """Build events whose |days_from_as_of| overlaps/ties to prove the sort
    key falls through event_type -> date_role -> source_event_id, not just
    abs(days_from_as_of) or event_date."""
    as_of = date(2026, 7, 13)

    # Two events land on the SAME event_date (so same days_from_as_of magnitude
    # and same event_date), tie-broken by event_type then source_event_id.
    same_day = as_of + timedelta(days=3)  # +3 days
    event_a_type_b = CorporateActionCalendarEvent(
        event_type=CorporateActionType.RIGHTS_ISSUE,  # "rights_issue"
        source_event_id="zzz-later",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.CUM_DATE, event_date=same_day
            ),
        ),
    )
    event_a_type_a = CorporateActionCalendarEvent(
        event_type=CorporateActionType.DIVIDEND,  # "dividend" < "rights_issue"
        source_event_id="aaa-earlier",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.CUM_DATE, event_date=same_day
            ),
        ),
    )
    # A far-away event (+2 days magnitude smaller) sorts first.
    closer_event = _dividend_event(
        as_of + timedelta(days=2), source_event_id="closer-1"
    )
    # A negative direction event with the same abs distance as the same_day
    # events (3 days) but earlier event_date sorts before them (event_date
    # tie-break comes before event_type when abs(days) ties but dates differ).
    # Uses rights_issue ex_date (lookback_days=5) since dividend ex_date's
    # lookback_days=2 would exclude a -3 day offset.
    earlier_date_event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.RIGHTS_ISSUE,
        source_event_id="past-1",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(
                date_role=CorporateActionDateRole.EX_DATE,
                event_date=as_of - timedelta(days=3),
            ),
        ),
    )

    repo = FakeCorporateActionCalendarRepository(
        [event_a_type_b, event_a_type_a, closer_event, earlier_date_event]
    )
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=_default_policy())

    response = use_case.execute(
        AssessCorporateActionEventRiskRequest(ticker="BBCA", as_of_date=as_of)
    )
    events = response.assessment.events

    # Expected order:
    # 1. closer_event: abs(days_from_as_of)=2
    # 2. earlier_date_event: abs=3, event_date=as_of-3d (earlier than same_day)
    # 3. event_a_type_a: abs=3, event_date=same_day, event_type="dividend"
    # 4. event_a_type_b: abs=3, event_date=same_day, event_type="rights_issue"
    assert [e.source_event_id for e in events] == [
        "closer-1",
        "past-1",
        "aaa-earlier",
        "zzz-later",
    ]
    assert [e.days_from_as_of for e in events] == [2, -3, 3, 3]


def test_repository_queried_with_max_configured_window_from_real_policy():
    as_of = date(2026, 7, 13)
    cfg = load_corporate_action_policy_config()
    repo = FakeCorporateActionCalendarRepository([])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=cfg)

    use_case.execute(AssessCorporateActionEventRiskRequest(ticker="bbca", as_of_date=as_of))

    assert len(repo.calls) == 1
    called_ticker, called_from, called_to = repo.calls[0]
    assert called_ticker == "BBCA"  # uppercased
    expected_from = as_of - timedelta(days=cfg.max_lookback_days())
    expected_to = as_of + timedelta(days=cfg.max_lookahead_days())
    assert called_from == expected_from
    assert called_to == expected_to


def test_lookback_and_lookahead_overrides_change_queried_window():
    as_of = date(2026, 7, 13)
    cfg = load_corporate_action_policy_config()
    repo = FakeCorporateActionCalendarRepository([])
    use_case = AssessCorporateActionEventRiskUseCase(repository=repo, policy=cfg)

    use_case.execute(
        AssessCorporateActionEventRiskRequest(
            ticker="BBCA",
            as_of_date=as_of,
            lookback_days_override=1,
            lookahead_days_override=2,
        )
    )

    assert len(repo.calls) == 1
    _, called_from, called_to = repo.calls[0]
    assert called_from == as_of - timedelta(days=1)
    assert called_to == as_of + timedelta(days=2)


def test_no_signal_engine_risk_engine_or_trade_setup_reference_in_source():
    """This use case must remain context/diagnostics only — it must never
    import or reference SignalEngine, RiskEngine, or TradeSetup in executable
    code. The module docstring explicitly documents this boundary (mentioning
    the names in prose), so we inspect only import statements and executable
    lines via `ast`, excluding docstrings/comments, rather than a raw
    substring search over the whole file."""
    import ast

    source_text = SRC_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(SRC_MODULE_PATH))

    forbidden_names = {"SignalEngine", "RiskEngine", "TradeSetup"}
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for name in forbidden_names:
                    if name in alias.name:
                        found.add(name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for name in forbidden_names:
                if name in module:
                    found.add(name)
            for alias in node.names:
                for name in forbidden_names:
                    if name in alias.name:
                        found.add(name)
        elif isinstance(node, ast.Name):
            if node.id in forbidden_names:
                found.add(node.id)
        elif isinstance(node, ast.Attribute):
            if node.attr in forbidden_names:
                found.add(node.attr)

    assert not found, (
        f"assess_corporate_action_event_risk_use_case.py must not reference "
        f"{found} in executable code (context/diagnostics only, ADR-026/032/033)"
    )
