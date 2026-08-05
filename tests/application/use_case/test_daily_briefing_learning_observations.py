from datetime import date, datetime
from unittest.mock import MagicMock

from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)


def test_daily_briefing_reads_pre_open_snapshot_from_learning_repository(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: ["BBCA"],
    )
    day = date(2026, 6, 19)
    observation = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="cohort",
        cutoff_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
        universe_id="iev:2026-06-19",
        window_id="BBCA:2026-06-19",
        decision_payload={
            "ticker": "BBCA",
            "candidate": {"iev": 10_000, "iep": 10_050, "trend": "UP"},
            "trade_setup": {"action": "ENTER"},
        },
        captured_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
        producer_source_revision="ai-saham@test",
    )
    learning_repository = MagicMock()
    learning_repository.list_observations.return_value = [observation]
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = []
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])

    response = DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning_repository,
    ).execute(DailyBriefingRequest(as_of_date=day))

    assert response.opening_snapshot_date == day
    assert response.opening_candidates[0].ticker == "BBCA"
    assert response.opening_candidates[0].opening_setup == "ENTER"
    learning_repository.list_observations.assert_called_once_with(
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
    )


def test_daily_briefing_enriches_pre_open_candidate_and_computes_delta_iev(
    monkeypatch,
) -> None:
    """ADR-052 Commit 2: surface the pre-open decision context stored in the corpus
    and compute delta_iev = decision_iev - 08:56 NCP baseline."""
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: ["BUMI"],
    )
    day = date(2026, 6, 19)
    observation = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="cohort",
        cutoff_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
        universe_id="iev:2026-06-19",
        window_id="BUMI:2026-06-19",
        decision_payload={
            "ticker": "BUMI",
            "candidate": {
                "iev": 796_137,
                "iep": 172,
                "trend": "UP",
                "prev_close": "170",
                "iep_gap_pct": "1.18",
                "iev_intensity": 0.0207,
                "bid_offer_imbalance": 0.969,
                "opening_broker_backing_score": 20.0,
                "opening_broker_backing_tag": "UNCONFIRMED",
                "trend_signal": "BULLISH",
                "entry_price": "171",
                "stop_loss_price": "168",
            },
            "trade_setup": {
                "action": "BLOCKED_EXECUTION",
                "signal_score": 55,
                "signal_strength": "MODERATE",
                "blocking_gates": ["BandarGate"],
                "rationale": "Signal 55/100 (MODERATE) | Blocked by BandarGate",
            },
        },
        captured_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
        producer_source_revision="ai-saham@test",
    )
    learning_repository = MagicMock()
    learning_repository.list_observations.return_value = [observation]
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = []
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])

    # Fake IEV baseline port: 08:56 NCP-locked baseline for BUMI = 715_997.
    iev_baseline = MagicMock()
    iev_baseline.ncp_baseline_iev.return_value = {"BUMI": 715_997}

    response = DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning_repository,
        iev_baseline_repository=iev_baseline,
    ).execute(DailyBriefingRequest(as_of_date=day))

    candidate = response.opening_candidates[0]
    assert candidate.ticker == "BUMI"
    assert candidate.opening_setup == "BLOCKED_EXECUTION"
    assert candidate.delta_iev == 796_137 - 715_997  # +80_140
    assert candidate.ncp_baseline_iev == 715_997
    assert candidate.iep_gap_pct == "1.18"
    assert candidate.prev_close == "170"
    assert candidate.bid_offer_imbalance == 0.969
    assert candidate.broker_backing_score == 20.0
    assert candidate.broker_backing_tag == "UNCONFIRMED"
    assert candidate.trend_signal == "BULLISH"
    assert candidate.entry_price == "171"
    assert candidate.stop_loss_price == "168"
    assert candidate.signal_score == 55
    assert candidate.signal_strength == "MODERATE"
    assert candidate.blocking_gates == ("BandarGate",)
    iev_baseline.ncp_baseline_iev.assert_called_once_with(day)


def test_daily_briefing_delta_iev_none_when_no_baseline(monkeypatch) -> None:
    """No 08:56 baseline for the ticker → delta_iev stays None (not a crash)."""
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: ["BUMI"],
    )
    day = date(2026, 6, 19)
    observation = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="cohort",
        cutoff_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
        universe_id="iev:2026-06-19",
        window_id="BUMI:2026-06-19",
        decision_payload={
            "ticker": "BUMI",
            "candidate": {"iev": 796_137, "iep": 172},
            "trade_setup": {"action": "WATCH"},
        },
        captured_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
        producer_source_revision="ai-saham@test",
    )
    learning_repository = MagicMock()
    learning_repository.list_observations.return_value = [observation]
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = []
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])

    iev_baseline = MagicMock()
    iev_baseline.ncp_baseline_iev.return_value = {}  # no baseline

    response = DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning_repository,
        iev_baseline_repository=iev_baseline,
    ).execute(DailyBriefingRequest(as_of_date=day))

    candidate = response.opening_candidates[0]
    assert candidate.iev == 796_137
    assert candidate.delta_iev is None
    assert candidate.ncp_baseline_iev is None


def _preopen_observation(day, iep=172):
    return LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="cohort",
        cutoff_at=datetime(day.year, day.month, day.day, 8, 57, tzinfo=IDX_TIMEZONE),
        universe_id=f"iev:{day.isoformat()}",
        window_id=f"BUMI:{day.isoformat()}",
        decision_payload={
            "ticker": "BUMI",
            "candidate": {"iev": 796_137, "iep": iep},
            "trade_setup": {"action": "WATCH"},
        },
        captured_at=datetime(day.year, day.month, day.day, 8, 57, tzinfo=IDX_TIMEZONE),
        producer_source_revision="ai-saham@test",
    )


def test_daily_briefing_reconciles_realized_open_vs_iep(monkeypatch):
    """ADR-052 Commit 6: when the session candle is cached, show realized open vs IEP."""
    from decimal import Decimal
    from types import SimpleNamespace

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: ["BUMI"],
    )
    day = date(2026, 6, 19)
    learning_repository = MagicMock()
    learning_repository.list_observations.return_value = [_preopen_observation(day, iep=172)]
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = [SimpleNamespace(date=day, open=Decimal("174"))]
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])

    response = DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning_repository,
    ).execute(DailyBriefingRequest(as_of_date=day))

    candidate = response.opening_candidates[0]
    assert candidate.realized_open == "174"
    assert candidate.realized_vs_iep_pct == round((174 - 172) / 172 * 100, 2)  # 1.16


def test_daily_briefing_realized_open_none_when_no_candle(monkeypatch):
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: ["BUMI"],
    )
    day = date(2026, 6, 19)
    learning_repository = MagicMock()
    learning_repository.list_observations.return_value = [_preopen_observation(day)]
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = []  # session candle not cached
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])

    response = DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning_repository,
    ).execute(DailyBriefingRequest(as_of_date=day))

    candidate = response.opening_candidates[0]
    assert candidate.realized_open is None
    assert candidate.realized_vs_iep_pct is None
