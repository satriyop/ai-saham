"""Tests for corporate action event-risk value objects.

Layer: Domain. Context/display only — never consumed by SignalEngine,
RiskEngine, or TradeSetup composition.
"""

from __future__ import annotations

from datetime import date

from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskFlag,
    CorporateActionEventRiskSeverity,
    CorporateActionRiskAssessment,
    CorporateActionRiskEvent,
)


def test_severity_enum_has_exactly_four_values_with_exact_strings():
    values = {member.value for member in CorporateActionEventRiskSeverity}
    assert values == {"none", "info", "warning", "blocking"}
    assert len(CorporateActionEventRiskSeverity) == 4


def test_severity_rank_orders_none_lt_info_lt_warning_lt_blocking():
    assert (
        CorporateActionEventRiskSeverity.NONE.rank
        < CorporateActionEventRiskSeverity.INFO.rank
        < CorporateActionEventRiskSeverity.WARNING.rank
        < CorporateActionEventRiskSeverity.BLOCKING.rank
    )


def test_flag_enum_has_exactly_seven_values_with_exact_strings():
    values = {member.value for member in CorporateActionEventRiskFlag}
    assert values == {
        "price_distortion",
        "volume_distortion",
        "liquidity_distortion",
        "special_situation",
        "governance_context",
        "disclosure_context",
        "new_listing",
    }
    assert len(CorporateActionEventRiskFlag) == 7


def _event(
    *,
    event_type: str = "dividend",
    date_role: str = "ex_date",
    event_date: date = date(2026, 7, 15),
    days_from_as_of: int = 2,
    severity: CorporateActionEventRiskSeverity = CorporateActionEventRiskSeverity.WARNING,
    flags: tuple[CorporateActionEventRiskFlag, ...] = (),
    note: str | None = None,
    source_event_id: str = "evt-1",
) -> CorporateActionRiskEvent:
    return CorporateActionRiskEvent(
        event_type=event_type,
        date_role=date_role,
        event_date=event_date,
        days_from_as_of=days_from_as_of,
        severity=severity,
        flags=flags,
        note=note,
        source_event_id=source_event_id,
    )


def test_assessment_with_no_events_is_a_valid_coherent_none_state():
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.NONE,
        events=(),
        rationale="No configured event risk for BBCA in the queried window.",
        nearest_event_date=None,
    )

    assert assessment.severity == CorporateActionEventRiskSeverity.NONE
    assert assessment.events == ()
    assert assessment.nearest_event_date is None
    assert assessment.has_price_distortion_risk is False
    assert assessment.has_volume_distortion_risk is False
    assert assessment.has_liquidity_distortion_risk is False
    assert assessment.has_special_situation_risk is False


def test_has_price_distortion_risk_true_when_any_event_carries_flag():
    events = (
        _event(flags=(CorporateActionEventRiskFlag.PRICE_DISTORTION,)),
        _event(
            event_type="rups",
            date_role="rups_date",
            severity=CorporateActionEventRiskSeverity.INFO,
            flags=(CorporateActionEventRiskFlag.GOVERNANCE_CONTEXT,),
            source_event_id="evt-2",
        ),
    )
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.WARNING,
        events=events,
        rationale="dividend ex_date on 2026-07-15 (warning); rups rups_date on 2026-07-15 (info)",
        nearest_event_date=events[0].event_date,
    )

    assert assessment.has_price_distortion_risk is True
    assert assessment.has_volume_distortion_risk is False
    assert assessment.has_liquidity_distortion_risk is False
    assert assessment.has_special_situation_risk is False


def test_has_liquidity_and_special_situation_risk_flags_detected_independently():
    events = (
        _event(
            event_type="rights_issue",
            date_role="ex_date",
            flags=(
                CorporateActionEventRiskFlag.PRICE_DISTORTION,
                CorporateActionEventRiskFlag.LIQUIDITY_DISTORTION,
            ),
            source_event_id="evt-3",
        ),
        _event(
            event_type="tender_offer",
            date_role="offer_start",
            flags=(CorporateActionEventRiskFlag.SPECIAL_SITUATION,),
            source_event_id="evt-4",
        ),
    )
    assessment = CorporateActionRiskAssessment(
        ticker="ANTM",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.WARNING,
        events=events,
        rationale="rights_issue ex_date; tender_offer offer_start",
        nearest_event_date=events[0].event_date,
    )

    assert assessment.has_liquidity_distortion_risk is True
    assert assessment.has_special_situation_risk is True
    assert assessment.has_price_distortion_risk is True
    assert assessment.has_volume_distortion_risk is False


def test_has_volume_distortion_risk_false_when_no_event_carries_flag():
    events = (
        _event(flags=(CorporateActionEventRiskFlag.PRICE_DISTORTION,)),
    )
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.WARNING,
        events=events,
        rationale="dividend ex_date",
        nearest_event_date=events[0].event_date,
    )

    assert assessment.has_volume_distortion_risk is False


def test_to_dict_round_trips_key_fields():
    events = (
        _event(
            event_type="stock_split",
            date_role="ex_date",
            event_date=date(2026, 7, 20),
            days_from_as_of=7,
            flags=(
                CorporateActionEventRiskFlag.PRICE_DISTORTION,
                CorporateActionEventRiskFlag.VOLUME_DISTORTION,
            ),
            note="1:2 split",
            source_event_id="evt-5",
        ),
    )
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.WARNING,
        events=events,
        rationale="stock_split ex_date on 2026-07-20 (warning)",
        nearest_event_date=date(2026, 7, 20),
    )

    d = assessment.to_dict()

    assert d["ticker"] == "BBCA"
    assert d["as_of_date"] == "2026-07-13"
    assert d["severity"] == "warning"
    assert d["nearest_event_date"] == "2026-07-20"
    assert d["rationale"] == "stock_split ex_date on 2026-07-20 (warning)"
    assert len(d["events"]) == 1

    event_dict = d["events"][0]
    assert event_dict["event_type"] == "stock_split"
    assert event_dict["date_role"] == "ex_date"
    assert event_dict["event_date"] == "2026-07-20"
    assert event_dict["days_from_as_of"] == 7
    assert event_dict["severity"] == "warning"
    assert event_dict["flags"] == ["price_distortion", "volume_distortion"]
    assert event_dict["note"] == "1:2 split"
    assert event_dict["source_event_id"] == "evt-5"


def test_to_dict_nearest_event_date_none_when_no_events():
    assessment = CorporateActionRiskAssessment(
        ticker="BBCA",
        as_of_date=date(2026, 7, 13),
        severity=CorporateActionEventRiskSeverity.NONE,
        events=(),
        rationale="No configured event risk for BBCA in the queried window.",
        nearest_event_date=None,
    )

    d = assessment.to_dict()

    assert d["nearest_event_date"] is None
    assert d["events"] == []
