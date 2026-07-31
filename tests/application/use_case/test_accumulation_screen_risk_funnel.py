"""Risk/filter funnel behavior tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _make_use_case_with_all_providers,
    _make_use_case_with_fundamentals,
    _summary,
    _weekdays,
    execute_and_record,
    make_signal_evidence_execution_context,
)


def test_min_piotroski_zero_does_not_filter():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=3)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=0,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 1


def test_min_piotroski_excludes_below_threshold():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=3)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=5,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 0


def test_min_piotroski_includes_at_threshold():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=5)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=5,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 1


def test_min_piotroski_excludes_when_no_fundamentals():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=None)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=4,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 0


def test_min_piotroski_passes_when_no_fundamentals_and_gate_disabled():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=None)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=0,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 1


def test_market_cap_floor_excludes_below_threshold():
    use_case, as_of, fund_prov, *_ = _make_use_case_with_all_providers(
        market_cap_idr=500_000_000_000,
        piotroski_score=8,  # 500B IDR < 1T floor
    )
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_market_cap_idr=1_000_000_000_000,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 0
    assert response.tickers_skipped == 1


def test_market_cap_floor_includes_at_or_above_threshold():
    use_case, as_of, *_ = _make_use_case_with_all_providers(
        market_cap_idr=2_000_000_000_000,
        piotroski_score=8,  # 2T IDR >= 1T floor
    )
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_market_cap_idr=1_000_000_000_000,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 1


def test_market_cap_floor_skips_enrichment_for_rejected_ticker():
    """Enrichment providers must NOT be called when market cap gate rejects the ticker."""
    use_case, as_of, fund_prov, seasonality_prov, bandar_prov, analyst_prov = (
        _make_use_case_with_all_providers(
            market_cap_idr=100_000_000_000,
            piotroski_score=8,  # 100B IDR < 1T floor
        )
    )
    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_market_cap_idr=1_000_000_000_000,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    # Fundamentals fetched once for the gate check
    fund_prov.get_fundamentals.assert_called_once()
    # All other enrichment skipped
    seasonality_prov.get_seasonal_edge.assert_not_called()
    bandar_prov.get_snapshot.assert_not_called()
    analyst_prov.get_consensus.assert_not_called()


def test_piotroski_gate_skips_enrichment_for_rejected_ticker():
    """Enrichment providers must NOT be called when piotroski gate rejects the ticker."""
    use_case, as_of, fund_prov, seasonality_prov, bandar_prov, analyst_prov = (
        _make_use_case_with_all_providers(
            market_cap_idr=5_000_000_000_000,
            piotroski_score=2,  # f-score 2 < floor 5
        )
    )
    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=5,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    fund_prov.get_fundamentals.assert_called_once()
    seasonality_prov.get_seasonal_edge.assert_not_called()
    bandar_prov.get_snapshot.assert_not_called()
    analyst_prov.get_consensus.assert_not_called()


def test_no_gate_active_fundamentals_fetched_in_enrichment_pass():
    use_case, as_of, fund_prov, *_ = _make_use_case_with_all_providers(
        market_cap_idr=2_000_000_000_000,
        piotroski_score=8,
    )
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            # No gate — min_market_cap_idr=0 and min_piotroski=0 (defaults)
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 1
    # Fundamentals still fetched exactly once (in enrichment pass, not gate pass)
    fund_prov.get_fundamentals.assert_called_once()


def test_screen_persists_rejected_candidates_with_filter_outcome():
    """Candidates rejected by min_accum_score are still persisted as
    negative samples for future tuning."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = execute_and_record(
        use_case,
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_accum_score=9999.0,  # impossible threshold — all rejected
            min_accum_score_enabled=True,
        ),
    )

    # No survivors — rejected by flow score threshold
    assert len(response.candidates) == 0
    # Rejected candidate still persisted as a learnable negative sample (ADR-056
    # session observation with per-window screen_results).
    assert len(spy_repo.saved) == 1
    payload = spy_repo.saved[0].decision_payload
    assert payload["ticker"] == "BBCA"
    assert payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    by_window = payload.get("screen_results_by_window") or {}
    assert by_window.get("7") == "rejected_flow"
