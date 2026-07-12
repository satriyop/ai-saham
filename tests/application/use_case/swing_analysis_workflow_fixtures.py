from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.application.dto.swing_analysis import SwingAnalysisWorkflowRequest
from src.application.use_case.swing_analysis_workflow_use_case import SwingAnalysisWorkflowUseCase
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation


class FakeMarketRepository:
    def __init__(self, candles: list[Candle], source: str | None = None) -> None:
        self._candles = candles
        self._source = source

    def get_candles(self, ticker: str, start_date=None, end_date=None):
        return self._candles

    def get_candle_source(self, ticker: str, on_date: date):
        return self._source


class FakeBrokerRepository:
    pass


class FakeCandidateObservationsRepository:
    def __init__(self, phases: tuple[str, ...]) -> None:
        self._phases = phases

    def save_many(self, observations):
        raise AssertionError("not used")

    def get_latest(self, ticker, snapshot_date):
        raise AssertionError("not used")

    def get_at(self, ticker, snapshot_date, captured_at):
        raise AssertionError("not used")

    def list_recent(self, ticker, *, before_date=None, limit=20):
        rows = []
        start = date(2026, 6, 1)
        for idx, phase in enumerate(self._phases):
            day = start + timedelta(days=idx)
            rows.append(
                CandidateObservation(
                    ticker=ticker.upper(),
                    snapshot_date=day,
                    captured_at=datetime(day.year, day.month, day.day, 9, 0, 0),
                    payload={
                        "schema_version": 1,
                        "workflow": "screen_accum",
                        "sub_signal_fingerprint": {
                            "setup_family": "foreign-bounce",
                            "setup_phase_current": phase,
                        },
                    },
                )
            )
        return list(reversed(rows))[:limit]


class FakeRegistry:
    def compute(self, name: str, candles: list[Candle], period: int):
        if name == "ATR":
            return [(candles[-1].date, Decimal("25"))]
        return []


def _candle(day: date) -> Candle:
    return Candle(
        ticker="BBCA",
        date=day,
        open=Decimal("1000"),
        high=Decimal("1025"),
        low=Decimal("990"),
        close=Decimal("1010"),
        volume=1_000_000,
    )


def _candle_with_close(day: date, close: str) -> Candle:
    return Candle(
        ticker="IHSG",
        date=day,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1_000_000,
    )


def _breakout_candles() -> list[Candle]:
    start = date(2026, 5, 30)
    candles = []
    for idx in range(21):
        open_ = Decimal("1000")
        high = Decimal("1010")
        close = Decimal("1005")
        if idx < 15:
            volume = 2_000_000
        elif idx < 20:
            volume = 800_000
        else:
            volume = 1_600_000
        if idx == 20:
            open_ = Decimal("1015")
            close = Decimal("1050")
            high = Decimal("1060")
        candles.append(
            Candle(
                ticker="BBCA",
                date=start + timedelta(days=idx),
                open=open_,
                high=high,
                low=Decimal("990"),
                close=close,
                volume=volume,
            )
        )
    return candles


def _request(**overrides) -> SwingAnalysisWorkflowRequest:
    values = {
        "ticker": "BBCA",
        "today": date(2026, 6, 18),
        "strategy_name": None,
        "setup_name": None,
        "window": 7,
        "flow_window": 30,
        "capital": None,
        "risk_pct": 1.0,
        "entry_price": None,
        "atr_mult": 1.5,
        "rr": 2.0,
        "include_sentiment": False,
        "include_flow_detail": False,
        "include_signal_detail": False,
        "include_risk_detail": False,
        "include_market_detail": False,
        "sentiment_verbose": False,
        "auto_refresh": False,
        "force_refresh": False,
        "with_market_context": False,
        "regime_universe": "idx80",
        "benchmark": "IHSG",
        "db_path": Path("data.db"),
        "with_technical_gate": False,
    }
    values.update(overrides)
    return SwingAnalysisWorkflowRequest(**values)


def _workflow(market_repo, calls: list[str]) -> SwingAnalysisWorkflowUseCase:
    return SwingAnalysisWorkflowUseCase(
        market_repository=market_repo,
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: calls.append("refresh") or ("candles=ok",),
        build_data_freshness=lambda **kwargs: {"freshness": kwargs["refresh_actions"]},
        build_flow_detail=lambda **kwargs: {"flow_window": kwargs["window_sessions"]},
        build_broker_detail=lambda **kwargs: {"broker_window": kwargs["window_sessions"]},
        build_accumulation_candidate=lambda **kwargs: {"ticker": kwargs["ticker"]},
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
    )
