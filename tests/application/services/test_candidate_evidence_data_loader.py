"""Tests for CandidateEvidenceDataLoader: shared evidence-family data loading."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.application.services.candidate_evidence_data_loader import (
    CandidateEvidenceDataLoader,
)
from src.domain.entities.candle import Candle


class _RecordingMarketRepository:
    def __init__(self, candles_by_ticker: dict[str, list[Candle]] | None = None) -> None:
        self._candles_by_ticker = candles_by_ticker or {}
        self.get_candles_calls: list[dict] = []

    def get_candles(self, ticker, start_date=None, end_date=None):
        self.get_candles_calls.append(
            {"ticker": ticker, "start_date": start_date, "end_date": end_date}
        )
        if ticker == "PEER_FAIL":
            raise RuntimeError("peer candle fetch failed")
        return list(self._candles_by_ticker.get(ticker, []))


class _RecordingBrokerRepository:
    def __init__(self) -> None:
        self.get_broker_daily_flows_calls: list[dict] = []
        self.get_foreign_flow_points_calls: list[dict] = []
        self.get_broker_summaries_calls: list[dict] = []

    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        self.get_broker_daily_flows_calls.append(
            {"ticker": ticker, "start_date": start_date, "end_date": end_date}
        )
        return []

    def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
        self.get_foreign_flow_points_calls.append(
            {"ticker": ticker, "start_date": start_date, "end_date": end_date}
        )
        return []

    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        self.get_broker_summaries_calls.append(
            {"ticker": ticker, "start_date": start_date, "end_date": end_date}
        )
        return []


def _candles(ticker: str, start: date, count: int) -> list[Candle]:
    return [
        Candle(
            ticker=ticker,
            date=date.fromordinal(start.toordinal() + i),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100") + Decimal(i),
            volume=1_000_000,
        )
        for i in range(count)
    ]


class TestLoadInstitutionalInputs:
    def test_uses_snapshot_date_minus_45_days_window(self):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository()
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)

        loader.load_institutional_inputs(ticker="BBCA", snapshot_date=snapshot_date)

        expected_start = snapshot_date - timedelta(days=45)
        for calls in (
            broker_repo.get_broker_daily_flows_calls,
            broker_repo.get_foreign_flow_points_calls,
            broker_repo.get_broker_summaries_calls,
        ):
            assert len(calls) == 1
            assert calls[0]["start_date"] == expected_start
            assert calls[0]["end_date"] == snapshot_date

    def test_broker_calls_share_the_same_date_window(self):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository()
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)

        loader.load_institutional_inputs(ticker="BBCA", snapshot_date=snapshot_date)

        windows = {
            (c["start_date"], c["end_date"])
            for c in (
                broker_repo.get_broker_daily_flows_calls
                + broker_repo.get_foreign_flow_points_calls
                + broker_repo.get_broker_summaries_calls
            )
        }
        assert windows == {(snapshot_date - timedelta(days=45), snapshot_date)}

    def test_fetches_candles_with_end_date_when_not_supplied(self):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository({"BBCA": _candles("BBCA", date(2026, 6, 1), 5)})
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)

        inputs = loader.load_institutional_inputs(ticker="BBCA", snapshot_date=snapshot_date)

        assert len(market_repo.get_candles_calls) == 1
        assert market_repo.get_candles_calls[0]["end_date"] == snapshot_date
        assert len(inputs.candles) == 5

    def test_reuses_supplied_candles_without_fetching(self):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository()
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)
        supplied = _candles("BBCA", date(2026, 6, 1), 3)

        inputs = loader.load_institutional_inputs(
            ticker="BBCA", snapshot_date=snapshot_date, candles=supplied
        )

        assert market_repo.get_candles_calls == []
        assert inputs.candles == tuple(supplied)


class TestLoadTickerProfileInputs:
    def test_uses_snapshot_date_minus_45_days_window(self):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository()
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)

        loader.load_ticker_profile_inputs(ticker="BBCA", snapshot_date=snapshot_date)

        expected_start = snapshot_date - timedelta(days=45)
        assert broker_repo.get_broker_daily_flows_calls[0]["start_date"] == expected_start
        assert broker_repo.get_broker_daily_flows_calls[0]["end_date"] == snapshot_date
        assert broker_repo.get_broker_summaries_calls[0]["start_date"] == expected_start
        assert broker_repo.get_broker_summaries_calls[0]["end_date"] == snapshot_date


class TestLoadSectorContextInputs:
    def test_peer_candle_failures_are_swallowed_and_successful_peers_remain(self):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository(
            {
                "PEER_OK": _candles("PEER_OK", date(2026, 6, 1), 4),
            }
        )
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)

        inputs = loader.load_sector_context_inputs(
            ticker="BBCA",
            snapshot_date=snapshot_date,
            sector="Financials",
            peer_tickers=("PEER_OK", "PEER_FAIL"),
            benchmark="IHSG",
        )

        assert "PEER_OK" in inputs.peer_candles
        assert len(inputs.peer_candles["PEER_OK"]) == 4
        assert "PEER_FAIL" not in inputs.peer_candles

    def test_all_candle_calls_pass_end_date_snapshot_date(self):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository(
            {"PEER_OK": _candles("PEER_OK", date(2026, 6, 1), 4)}
        )
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)

        loader.load_sector_context_inputs(
            ticker="BBCA",
            snapshot_date=snapshot_date,
            sector=None,
            peer_tickers=("PEER_OK",),
            benchmark="IHSG",
        )

        for call in market_repo.get_candles_calls:
            assert call["end_date"] == snapshot_date

    def test_benchmark_return_preserves_lookback_and_min_valid(self, monkeypatch):
        snapshot_date = date(2026, 6, 15)
        market_repo = _RecordingMarketRepository()
        broker_repo = _RecordingBrokerRepository()
        loader = CandidateEvidenceDataLoader(market_repo, broker_repo)

        captured = {}

        def fake_benchmark_return_from_repository(
            repository, *, benchmark, end_date, lookback, min_valid
        ):
            captured["lookback"] = lookback
            captured["min_valid"] = min_valid
            captured["benchmark"] = benchmark
            captured["end_date"] = end_date
            return 0.05

        monkeypatch.setattr(
            "src.application.services.candidate_evidence_data_loader.benchmark_return_from_repository",
            fake_benchmark_return_from_repository,
        )

        inputs = loader.load_sector_context_inputs(
            ticker="BBCA",
            snapshot_date=snapshot_date,
            sector=None,
            peer_tickers=(),
            benchmark="IHSG",
        )

        assert captured == {
            "lookback": 20,
            "min_valid": 18,
            "benchmark": "IHSG",
            "end_date": snapshot_date,
        }
        assert inputs.ihsg_20d_return == 0.05
