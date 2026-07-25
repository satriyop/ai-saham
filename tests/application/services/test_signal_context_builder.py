from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.signal_engine import SignalEngine
from src.domain.value_objects.forward_estimates import ForwardEstimates


def test_signal_context_builder_derives_forward_pe_and_preserves_insider_ratio():
    candidate = SimpleNamespace(
        accum_score=50.0,
        current_price=Decimal("125"),
        insider_net_buy_ratio=0.25,
        bandar_detector=None,
        seasonal_edge=None,
        analyst_consensus=None,
        forward_estimates=ForwardEstimates(
            ticker="BBCA",
            forward_eps_1y=10.0,
            revenue_forward_1y=None,
            current_price=None,
            forward_pe=None,
        ),
    )

    ctx = build_signal_context_from_candidate(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 27),
        candidate=candidate,
        signal_engine=SignalEngine(),
    )

    assert ctx.foreign_flow_quality == 0.5
    assert ctx.insider_net_buy_ratio == 0.25
    assert ctx.forward_pe == 12.5


def test_signal_context_builder_without_accum_score_yields_none_foreign_flow_quality():
    """Absent accum_score is first-class; foreign_flow_quality stays None."""
    candidate = SimpleNamespace(
        current_price=Decimal("100"),
        insider_net_buy_ratio=None,
        bandar_detector=None,
        seasonal_edge=None,
        analyst_consensus=None,
        forward_estimates=None,
    )

    ctx = build_signal_context_from_candidate(
        ticker="BBRI",
        snapshot_date=date(2026, 6, 27),
        candidate=candidate,
        signal_engine=SignalEngine(),
    )

    assert ctx.foreign_flow_quality is None
    assert ctx.ticker == "BBRI"


def test_signal_context_builder_explicit_none_accum_score_yields_none_foreign_flow():
    candidate = SimpleNamespace(
        accum_score=None,
        bandar_detector=None,
        seasonal_edge=None,
        analyst_consensus=None,
        forward_estimates=None,
    )

    ctx = build_signal_context_from_candidate(
        ticker="TLKM",
        snapshot_date=date(2026, 6, 27),
        candidate=candidate,
        signal_engine=SignalEngine(),
    )

    assert ctx.foreign_flow_quality is None
