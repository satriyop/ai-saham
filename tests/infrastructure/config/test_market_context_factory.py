from datetime import date

from src.infrastructure.config import market_context_factory
from src.infrastructure.config.market_context_factory import (
    create_market_context_engine,
    evaluate_market_context,
)


def test_create_market_context_engine_resolves_universe_and_overrides_benchmark(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        market_context_factory,
        "resolve_tickers",
        lambda universe, explicit, db_path: ["bbca", "bbri"],
    )

    engine = create_market_context_engine(
        db_path=tmp_path / "data.db",
        universe="lq45",
        benchmark="CUSTOM",
    )

    assert engine._universe == ["BBCA", "BBRI"]
    assert engine._config.idx_trend.benchmark_ticker == "CUSTOM"


def test_evaluate_market_context_delegates_to_factory_engine(tmp_path, monkeypatch):
    calls = []
    expected = object()

    class FakeEngine:
        def evaluate(self, as_of_date):
            calls.append(as_of_date)
            return expected

    monkeypatch.setattr(
        market_context_factory,
        "create_market_context_engine",
        lambda **kwargs: FakeEngine(),
    )

    result = evaluate_market_context(
        db_path=tmp_path / "data.db",
        as_of_date=date(2026, 6, 18),
        universe="idx80",
        benchmark="^JKSE",
    )

    assert result is expected
    assert calls == [date(2026, 6, 18)]
