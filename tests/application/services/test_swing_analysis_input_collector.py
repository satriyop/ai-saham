"""Tests for SwingAnalysisInputCollector date threading.

Focused proof that ``request.today`` reaches the accumulation-candidate builder
so historical ``--date`` mode stays internally consistent.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from src.application.dto.swing_analysis import SwingAnalysisWorkflowRequest
from src.application.services.swing_analysis_input_collector import (
    SwingAnalysisInputCollector,
)


def _request(today: date) -> SwingAnalysisWorkflowRequest:
    return SwingAnalysisWorkflowRequest(
        ticker="BBRI",
        today=today,
        strategy_name=None,
        setup_name=None,
        window=200,
        flow_window=20,
        capital=None,
        risk_pct=1.0,
        entry_price=None,
        atr_mult=2.0,
        rr=2.0,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=False,
        include_risk_detail=False,
        include_market_detail=False,
        sentiment_verbose=False,
        auto_refresh=False,
        force_refresh=False,
        with_market_context=False,
        regime_universe="lq45",
        benchmark="COMPOSITE",
        db_path=Path("/tmp/does-not-exist.db"),
    )


def test_accumulation_builder_receives_request_today():
    # A fixed historical date that is NOT date.today().
    historical = date(2025, 1, 15)
    assert historical != date.today()

    received: dict = {}

    def build_accumulation_candidate(**kwargs):
        received.update(kwargs)
        return None

    market_repo = SimpleNamespace(
        get_candles=lambda ticker: [SimpleNamespace(close=100.0)]
    )
    # This test proves request.today threading into the accumulation
    # builder, not effective-session resolution — inject a fake resolver so
    # the real resolver's IHSG get_candles(end_date=...) lookup (which this
    # market_repo fake does not implement) is never invoked.
    collector = SwingAnalysisInputCollector(
        market_repository=market_repo,
        broker_repository=SimpleNamespace(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate=build_accumulation_candidate,
        evaluate_market_context=None,
        session_resolver=SimpleNamespace(resolve=lambda **kwargs: None),
    )

    collector.collect(_request(historical))

    assert received["as_of_date"] == historical
    assert received["ticker"] == "BBRI"
    assert received["window"] == 200
