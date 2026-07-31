from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from src.application.dto.plan_swing import PlanSwingWorkflowRequest
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.application.use_case.plan_swing_workflow_use_case import PlanSwingWorkflowUseCase
from src.domain.entities.candle import Candle
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


def _fake_signal_evidence_context_builder() -> SignalEvidenceExecutionContextBuilder:
    return SignalEvidenceExecutionContextBuilder(trading_session_calendar_loader=None)


class FakeMarketRepository:
    def __init__(self, candles: list[Candle], source: str | None = None) -> None:
        self._candles = candles
        self._source = source

    def get_candles(self, ticker: str, start_date=None, end_date=None):
        return self._candles

    def get_candle_source(self, ticker: str, on_date: date):
        return self._source


class FakeBrokerRepository:
    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        return []

    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        return []


class FakeLearningObservationsRepository:
    def __init__(self, phases: tuple[str, ...]) -> None:
        self._phases = phases

    def list_observations(self, purpose, *, compatibility_id=None):
        assert purpose is AssessmentPurpose.ACCUMULATION_DISCOVERY
        rows = []
        start = date(2026, 6, 1)
        for idx, phase in enumerate(self._phases):
            day = start + timedelta(days=idx)
            rows.append(
                LearningObservation.create(
                    purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                    policy_contract="test_policy.v1",
                    horizon_contract="test_horizon",
                    compatibility_id="test-cohort",
                    cutoff_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=IDX_TIMEZONE),
                    universe_id="test",
                    window_id=f"{idx}",
                    captured_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=IDX_TIMEZONE),
                    decision_payload={
                        "ticker": "BBCA",
                        "schema_version": 1,
                        "workflow": "screen_accum",
                        "sub_signal_fingerprint": {
                            "setup_family": "foreign-bounce",
                            "setup_phase_current": phase,
                        },
                    },
                )
            )
        return rows


class FakeSetupPhaseHistoryRepository:
    """ADR-058 production phase memory for sequence validation tests."""

    def __init__(self, phases: tuple[str, ...], *, ticker: str = "BBCA") -> None:
        from src.domain.ports.setup_phase_history_repository import (
            SCHEMA_VERSION_V1,
            SOURCE_WORKFLOW_SCREEN_ACCUM,
            SetupPhaseLedgerRow,
        )
        from src.domain.value_objects.setup_phase import SetupPhaseState

        self._rows: list[SetupPhaseLedgerRow] = []
        start = date(2026, 6, 1)
        for idx, phase_name in enumerate(phases):
            day = start + timedelta(days=idx)
            self._rows.append(
                SetupPhaseLedgerRow(
                    entry_id=f"test-{ticker}-{day.isoformat()}",
                    ticker=ticker.upper(),
                    as_of_date=day,
                    phase=SetupPhaseState(phase_name),
                    setup_family="foreign-bounce",
                    source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
                    recorded_at=datetime(
                        day.year, day.month, day.day, 9, 0, tzinfo=IDX_TIMEZONE
                    ).isoformat(),
                    schema_version=SCHEMA_VERSION_V1,
                )
            )

    def list_rows_before(self, *, ticker: str, before_date: date, limit: int | None = None):
        rows = [r for r in self._rows if r.ticker == ticker.upper() and r.as_of_date < before_date]
        if limit is not None:
            rows = rows[-limit:]
        return rows

    def list_rows_before_many(self, *, tickers, before_date: date):
        wanted = {str(t).upper() for t in tickers}
        return [r for r in self._rows if r.ticker in wanted and r.as_of_date < before_date]

    def record_phase(self, **kwargs):
        from src.domain.ports.setup_phase_history_repository import SetupPhaseRecordResult

        return SetupPhaseRecordResult.SKIPPED_POLICY


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


def _request(**overrides) -> PlanSwingWorkflowRequest:
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
    return PlanSwingWorkflowRequest(**values)


def _fake_evaluation_result(ticker: str) -> SimpleNamespace:
    """Minimal stand-in for AccumulationCandidateEvaluationResult — a
    `.candidate` plus the empty consumed-row tuples these tests' fake
    repositories always return."""
    return SimpleNamespace(
        candidate={"ticker": ticker},
        consumed_candles=(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    )


def _workflow(market_repo, calls: list[str]) -> PlanSwingWorkflowUseCase:
    return PlanSwingWorkflowUseCase(
        market_repository=market_repo,
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: calls.append("refresh") or ("candles=ok",),
        build_data_freshness=lambda **kwargs: {"freshness": kwargs["refresh_actions"]},
        build_flow_detail=lambda **kwargs: {"flow_window": kwargs["window_sessions"]},
        build_broker_detail=lambda **kwargs: {"broker_window": kwargs["window_sessions"]},
        build_accumulation_candidate_evaluation=lambda **kwargs: _fake_evaluation_result(
            kwargs["ticker"]
        ),
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_policy_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=RulesYamlLoader(),
        signal_evidence_context_builder=_fake_signal_evidence_context_builder(),
    )
