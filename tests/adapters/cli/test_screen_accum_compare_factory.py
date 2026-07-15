"""Tests for run_fresh_accumulation_screen_for_compare."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from src.adapters.cli.screen_accum_compare_factory import (
    run_fresh_accumulation_screen_for_compare,
)
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
)


def _fake_candidate(ticker: str, score: float = 70.0) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=5 / 7,
        total_net_value=Decimal("10000000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1030"),
        current_price=Decimal("1000"),
        vwap_discount_pct=3.0,
        rsi=55.0,
        trend="SIDE",
        foreign_flow_score=score,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=5.0,
    )


_FAKE_SC = SimpleNamespace(
    tier1_broker_codes=frozenset(),
    bci_cluster_min_count=3,
    bci_stable_min_count=1,
    resistance_gate_enabled=False,
    resistance_headroom_min_pct=5.0,
    ex_date_warning_days=10,
)

_FAKE_ASC = SimpleNamespace()


def test_returns_top_candidates(monkeypatch):
    candidates = [
        _fake_candidate("BBCA", 80.0),
        _fake_candidate("BBRI", 70.0),
        _fake_candidate("BMRI", 60.0),
    ]

    def fake_resolve(**kwargs):
        return ["BBCA", "BBRI", "BMRI"]

    class FakeUseCase:
        def execute(self, request):
            return AccumulationScreenResponse(
                candidates=candidates,
                screened_at=date(2026, 7, 1),
                window_days=request.window_days,
                total_tickers_checked=3,
                tickers_skipped=0,
                provider="fake",
            )

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        fake_resolve,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.create_accumulation_screen_workflow",
        lambda **kwargs: SimpleNamespace(use_case=FakeUseCase()),
    )

    result = run_fresh_accumulation_screen_for_compare(
        universe="lq45",
        window=7,
        top=2,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert result is not None
    assert len(result) == 2
    assert result[0].ticker == "BBCA"
    assert result[1].ticker == "BBRI"


def test_returns_none_on_empty_universe(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        lambda **kwargs: [],
    )

    result = run_fresh_accumulation_screen_for_compare(
        universe="empty",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert result is None


def test_returns_none_on_exception(monkeypatch):
    def fake_resolve(**kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        fake_resolve,
    )

    result = run_fresh_accumulation_screen_for_compare(
        universe="boom",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert result is None


def test_builds_workflow_with_risk_false(monkeypatch):
    captured = {}

    def fake_resolve(**kwargs):
        return ["BBCA"]

    def fake_workflow(**kwargs):
        captured["with_risk"] = kwargs.get("with_risk")
        captured["screener_config"] = kwargs.get("screener_config")
        captured["swing_config"] = kwargs.get("swing_config")
        return SimpleNamespace(
            use_case=SimpleNamespace(
                execute=lambda req: AccumulationScreenResponse(
                    candidates=[_fake_candidate("BBCA")],
                    screened_at=date(2026, 7, 1),
                    window_days=req.window_days,
                    total_tickers_checked=1,
                    tickers_skipped=0,
                    provider="fake",
                )
            )
        )

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        fake_resolve,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.create_accumulation_screen_workflow",
        fake_workflow,
    )

    run_fresh_accumulation_screen_for_compare(
        universe="lq45",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert captured["with_risk"] is False
    assert captured["screener_config"] is _FAKE_ASC
    assert captured["swing_config"] is _FAKE_SC


def test_compare_writes_zero_candidate_observations(monkeypatch):
    """S1 regression: screen compare is read-only and must never persist
    observations, even with a real screen use case wired to a live repo."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()

    real_use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
    )

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.resolve_tickers",
        lambda **kwargs: ["BBCA"],
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.create_accumulation_screen_workflow",
        lambda **kwargs: SimpleNamespace(use_case=real_use_case),
    )

    run_fresh_accumulation_screen_for_compare(
        universe="lq45",
        window=7,
        top=10,
        db_path=Path("/tmp/fake.db"),
        screener_config=_FAKE_ASC,
        swing_config=_FAKE_SC,
    )

    assert spy_repo.saved == []
