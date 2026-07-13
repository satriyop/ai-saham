"""
Tests for RunAccumulationAuditWorkflowUseCase.

Uses fakes only — no infrastructure imports.
"""

from datetime import date

import pytest

from src.application.dto.accumulation_audit import (
    AccumulationAuditPolicy,
    AccumulationAuditRequest,
    AccumulationAuditResponse,
)
from src.application.use_case.run_accumulation_audit_workflow_use_case import (
    NoTickersError,
    RunAccumulationAuditWorkflowRequest,
    RunAccumulationAuditWorkflowUseCase,
)


class FakeAuditUseCase:
    def __init__(self) -> None:
        self.last_request: AccumulationAuditRequest | None = None

    def execute(self, request: AccumulationAuditRequest) -> AccumulationAuditResponse:
        self.last_request = request
        return AccumulationAuditResponse(
            start_date=request.start_date,
            end_date=request.end_date,
            window_days=request.window_days,
            total_replay_dates=1,
            total_tickers=len(request.tickers),
            total_records=0,
            skipped_no_forward_data=0,
            records=[],
            group_stats=[],
            exit_simulations=[],
            warnings=["some warning"],
        )


def _base_request(**overrides) -> RunAccumulationAuditWorkflowRequest:
    defaults = dict(
        tickers=["bbca"],
        universe=None,
        setup=None,
        start="2026-01-01",
        end="2026-01-10",
        window=None,
        min_foreign_flow_score=None,
        min_net_buy_days=None,
        min_vwap_disc=None,
        trend=None,
        min_flow_pct=None,
        require_rsi=False,
        max_rsi=None,
        min_rsi=None,
        max_bb_width_pctile=None,
        broker_quality=None,
        simulate_exits=None,
        take_profits=None,
        stop_losses=None,
        max_holds=None,
        horizon=None,
    )
    defaults.update(overrides)
    return RunAccumulationAuditWorkflowRequest(**defaults)


def _identity_resolve_tickers(*, universe, explicit):
    tickers = list(explicit)
    if universe:
        tickers.append(universe.upper())
    return [t.upper() for t in tickers]


def _make_workflow(audit_use_case=None, audit_setups=None, resolve_tickers=None):
    return RunAccumulationAuditWorkflowUseCase(
        audit_use_case=audit_use_case or FakeAuditUseCase(),
        audit_policy=AccumulationAuditPolicy(),
        audit_setups=audit_setups or {},
        resolve_tickers=resolve_tickers or _identity_resolve_tickers,
    )


def test_setup_preset_fills_missing_values():
    workflow = _make_workflow(
        audit_setups={"foreign-bounce": {"window": 12, "min_foreign_flow_score": 55.0}},
    )
    result = workflow.execute(_base_request(setup="foreign-bounce"))

    assert result.window == 12
    assert result.min_foreign_flow_score == 55.0


def test_explicit_cli_values_override_setup_preset():
    workflow = _make_workflow(
        audit_setups={"foreign-bounce": {"window": 12, "min_foreign_flow_score": 55.0}},
    )
    result = workflow.execute(
        _base_request(setup="foreign-bounce", window=3, min_foreign_flow_score=20.0)
    )

    assert result.window == 3
    assert result.min_foreign_flow_score == 20.0


def test_unknown_setup_raises_with_current_message():
    workflow = _make_workflow(audit_setups={"foreign-bounce": {}})

    with pytest.raises(
        ValueError, match=r"unknown setup 'bogus'\. Available setups: foreign-bounce"
    ):
        workflow.execute(_base_request(setup="bogus"))


def test_invalid_date_raises_with_current_message():
    workflow = _make_workflow()

    with pytest.raises(ValueError, match=r"invalid date format:"):
        workflow.execute(_base_request(start="not-a-date"))


def test_invalid_trend_raises_with_current_message():
    workflow = _make_workflow()

    with pytest.raises(ValueError, match=r"--trend must be one of: UP, SIDE, DOWN"):
        workflow.execute(_base_request(trend="SIDEWAYS"))


def test_invalid_float_grid_raises_with_current_message():
    workflow = _make_workflow()

    with pytest.raises(ValueError, match=r"--take-profits must be comma-separated numbers"):
        workflow.execute(_base_request(take_profits="a,b,c"))


def test_invalid_int_grid_raises_with_current_message():
    workflow = _make_workflow()

    with pytest.raises(ValueError, match=r"--max-holds must be comma-separated integers"):
        workflow.execute(_base_request(max_holds="a,b,c"))


def test_no_resolved_tickers_raises_no_tickers_error():
    workflow = _make_workflow(resolve_tickers=lambda *, universe, explicit: [])

    with pytest.raises(
        NoTickersError,
        match=r"No tickers to audit\. Specify --universe or provide ticker arguments\.",
    ):
        workflow.execute(_base_request(tickers=[]))


def test_calls_audit_use_case_with_expected_request():
    audit_use_case = FakeAuditUseCase()
    workflow = _make_workflow(audit_use_case=audit_use_case)

    workflow.execute(_base_request())

    sent = audit_use_case.last_request
    assert sent is not None
    assert sent.tickers == ["BBCA"]
    assert sent.start_date == date(2026, 1, 1)
    assert sent.end_date == date(2026, 1, 10)
    assert sent.window_days == 7
    assert sent.min_foreign_flow_score == 40.0
    assert sent.min_net_buy_days == 2
    assert sent.take_profit_pcts == (4.0, 5.0, 6.0)
    assert sent.stop_loss_pcts == (3.0, 5.0, 7.0)
    assert sent.max_hold_days == (3, 5, 7, 10)


def test_to_json_dict_preserves_current_schema_keys():
    workflow = _make_workflow()
    result = workflow.execute(_base_request())

    payload = result.to_json_dict()

    assert payload == {
        "schema_version": 1,
        "artifact_type": "accumulation_audit",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
        "window_days": 7,
        "total_replay_dates": 1,
        "total_tickers": 1,
        "total_records": 0,
        "skipped_no_forward_data": 0,
        "warnings": ["some warning"],
        "group_stats": [],
        "exit_simulations": [],
    }


def test_filter_label_includes_active_filters_in_current_wording_order():
    workflow = _make_workflow()
    result = workflow.execute(
        _base_request(
            min_vwap_disc=1.5,
            trend="up",
            min_flow_pct=5.0,
            require_rsi=True,
            max_rsi=70.0,
            min_rsi=30.0,
            max_bb_width_pctile=0.4,
            broker_quality="smart+",
            simulate_exits=True,
        )
    )

    assert result.filter_label == (
        " | filters: VWAP>=1.5%, trend=UP, flow>=5%, RSI present, "
        "RSI<=70, RSI>=30, BBpct<=0.4, broker=smart+, exit simulation"
    )
