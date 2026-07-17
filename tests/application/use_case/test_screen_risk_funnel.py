"""
Phase E (Rec 14) — post-screening risk gating funnel.

Verifies:
- risk_assessment is None on candidates when no risk_use_case configured (opt-in)
- risk_assessment is populated on survivors when risk_use_case is configured
- FundamentalGate HIGH_RISK surfaces on the candidate's risk_assessment
- GateContext is built from pre-loaded candidate data (no duplicate provider calls)
- Graceful degradation: risk failure for one ticker does not abort others
- to_dict() includes risk_status, risk_confidence, risk_gate fields
"""

from datetime import date, datetime, timedelta
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.services.accumulation_risk_funnel import AccumulationRiskFunnel
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.assess_risk_use_case import AssessRiskResponse, AssessRiskUseCase
from src.application.use_case.assess_signal_use_case import AssessSignalResponse
from src.domain.entities.candle import Candle
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from src.domain.value_objects.trade_setup import SetupAction
from tests.application.use_case.accumulation_screen_fixtures import FakeRulesLoader

_TODAY = date(2026, 6, 23)


# ─── Shared helpers ───────────────────────────────────────────────────────────


def _flat_candles(ticker: str, count: int = 365, price: float = 5000.0) -> list[Candle]:
    return [
        Candle(
            ticker=ticker,
            date=_TODAY - timedelta(days=count - i),
            open=Decimal(str(price)),
            high=Decimal(str(price)),
            low=Decimal(str(price)),
            close=Decimal(str(price)),
            volume=2_000_000,
        )
        for i in range(count)
    ]


def _mock_market_repo(tickers: list[str]) -> MagicMock:
    """Market repo that returns flat candles for every requested ticker."""
    repo = MagicMock()

    def _get_candles(ticker, start_date=None, end_date=None):
        rows = _flat_candles(ticker)
        if start_date:
            rows = [c for c in rows if c.date >= start_date]
        if end_date:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    repo.get_candles.side_effect = _get_candles
    repo.get_date_range.return_value = (_TODAY - timedelta(days=365), _TODAY)
    return repo


def _mock_broker_repo() -> MagicMock:
    """Minimal broker repo stub — returns empty summaries.

    Most risk-funnel tests call AccumulationRiskFunnel directly with manually
    constructed candidates, so no real BrokerSummary data is needed.
    The repo is required only to satisfy AccumulationScreenUseCase's constructor.
    """
    repo = MagicMock()
    repo.get_summaries.return_value = []
    repo.get_date_range.return_value = None
    return repo


# ─── Opt-in: no risk_use_case → risk_assessment stays None ───────────────────


def test_risk_assessment_none_when_no_risk_use_case():
    """risk_use_case=None → funnel never runs → risk_assessment stays None."""
    mkt_repo = _mock_market_repo(["BBCA"])
    uc = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=_mock_broker_repo(),
        market_repository=mkt_repo,
        rules_loader=FakeRulesLoader(),
        risk_use_case=None,
    )
    context = SignalEvidenceExecutionContext(
        effective_session=EffectiveMarketSession(
            run_at=datetime.min,
            decision_at=datetime(2026, 6, 23, 16, 0),
            latest_completed_session=_TODAY,
            analysis_as_of=_TODAY,
            market_session_name="AFTER_CLOSE",
            is_eod_pending=False,
            resolution_source="test",
        ),
        source_availability_use_case=None,
    )
    resp = uc.execute(AccumulationScreenRequest(tickers=["BBCA"]), execution_context=context)
    for candidate in resp.candidates:
        assert candidate.risk_assessment is None


# ─── risk funnel with FundamentalGate ────────────────────────────────────────


def test_risk_funnel_fires_fundamental_gate_on_distressed_ticker():
    """Candidate with F-score=1 should get HIGH_RISK via FundamentalGate."""
    mkt_repo = _mock_market_repo(["BBCA"])
    risk_uc = AssessRiskUseCase(
        repository=mkt_repo,
        structural_gates=[FundamentalGate(distress_threshold=3)],
    )

    candidate = MagicMock()
    candidate.ticker = "BBCA"
    candidate.fundamentals = CompanyFundamentals(
        ticker="BBCA",
        pe_ratio_ttm=None, roe_ttm=None, net_profit_margin=None,
        revenue_yoy_growth=None, piotroski_f_score=1,  # distressed
        dividend_yield=None, week52_high=None, week52_low=None,
        near_52w_high_rank=None, market_cap_idr=2_000_000_000_000,
    )
    candidate.bandar_detector = None

    AccumulationRiskFunnel(risk_uc).run([candidate], _TODAY)

    assert candidate.risk_assessment is not None
    assert candidate.risk_assessment.gate_triggered is not None
    assert candidate.risk_assessment.gate_triggered == "FundamentalGate"


def test_risk_funnel_passes_healthy_ticker():
    """Candidate with F-score=8 should not get HIGH_RISK from FundamentalGate."""
    mkt_repo = _mock_market_repo(["BBCA"])
    risk_uc = AssessRiskUseCase(
        repository=mkt_repo,
        structural_gates=[FundamentalGate(distress_threshold=3)],
    )

    candidate = MagicMock()
    candidate.ticker = "BBCA"
    candidate.fundamentals = CompanyFundamentals(
        ticker="BBCA",
        pe_ratio_ttm=None, roe_ttm=None, net_profit_margin=None,
        revenue_yoy_growth=None, piotroski_f_score=8,  # healthy
        dividend_yield=None, week52_high=None, week52_low=None,
        near_52w_high_rank=None, market_cap_idr=2_000_000_000_000,
    )
    candidate.bandar_detector = None

    AccumulationRiskFunnel(risk_uc).run([candidate], _TODAY)

    assert candidate.risk_assessment is not None
    # FundamentalGate must not have fired (F-score=8 is healthy).
    # The technical engine may still return HIGH_RISK (e.g. RSI overbought on
    # flat candles) — that's fine; we're testing gate selectivity, not rule engine.
    assert candidate.risk_assessment.gate_triggered is None


def test_risk_funnel_composes_trade_setup_from_signal_and_risk():
    """screen accum final action must come from AssessTradeSetupUseCase."""
    signal_response = AssessSignalResponse(
        ticker="BBCA",
        assessment=SignalAssessment(
            ticker="BBCA",
            score=76,
            strength=SignalStrength.STRONG,
            entry_quality=EntryQuality.ENTER,
            breakdown=(("foreign_flow_quality", 80.0),),
            rationale=("signal supportive",),
            snapshot_date=_TODAY,
        ),
    )
    risk_response = AssessRiskResponse(
        ticker="BBCA",
        assessment=RiskAssessment(
            rationale=("no gate fired",),
            snapshot_date=_TODAY,
            indicators=IndicatorSnapshot(
                date=_TODAY,
                sma=Decimal("5000"),
                ema=Decimal("5000"),
                rsi=Decimal("50"),
            ),
            gate_triggered=None,
            gate_is_structural=None,
            gate_confidence=None,
        ),
        sma_period=20,
        ema_period=20,
        rsi_period=14,
    )
    risk_uc = MagicMock(spec=AssessRiskUseCase)
    risk_uc.execute.return_value = risk_response

    candidate = MagicMock()
    candidate.ticker = "BBCA"
    candidate.fundamentals = None
    candidate.shareholding = None
    candidate.bandar_detector = None
    candidate.signal_assessment = signal_response

    AccumulationRiskFunnel(risk_uc).run([candidate], _TODAY)

    assert candidate.risk_assessment == risk_response.assessment
    assert candidate.trade_setup is not None
    assert candidate.trade_setup.action == SetupAction.ENTER
    assert candidate.trade_setup.signal_score == 76


# ─── GateContext built from pre-loaded data ───────────────────────────────────


def test_risk_funnel_builds_gate_context_from_candidate_data():
    """GateContext fields must match candidate.fundamentals / bandar_detector — no re-query."""
    mkt_repo = _mock_market_repo(["BBCA"])
    captured_contexts: list = []

    class _CapturingGate:
        def evaluate(self, ctx):
            captured_contexts.append(ctx)
            from src.domain.rules.risk_gate import GateResult
            return GateResult(triggered=False, reason="pass", confidence=0)

    risk_uc = AssessRiskUseCase(
        repository=mkt_repo,
        structural_gates=[_CapturingGate()],
    )

    candidate = MagicMock()
    candidate.ticker = "BBCA"
    candidate.fundamentals = CompanyFundamentals(
        ticker="BBCA",
        pe_ratio_ttm=None, roe_ttm=None, net_profit_margin=None,
        revenue_yoy_growth=None, piotroski_f_score=7,
        dividend_yield=None, week52_high=None, week52_low=None,
        near_52w_high_rank=None, market_cap_idr=5_000_000_000_000,
    )
    candidate.bandar_detector = MagicMock()
    candidate.bandar_detector.five_day_accdist = "Big Acc"

    AccumulationRiskFunnel(risk_uc).run([candidate], _TODAY)

    assert len(captured_contexts) >= 1
    ctx = captured_contexts[0]
    assert ctx.piotroski_f_score == 7
    assert ctx.market_cap_idr == 5_000_000_000_000
    assert ctx.five_day_accdist == "Big Acc"


# ─── Graceful degradation ────────────────────────────────────────────────────


def test_risk_funnel_skips_failed_candidate_and_continues():
    """One failing ticker must not abort others — second candidate gets its assessment."""
    success_assessment = MagicMock()
    success_assessment.gate_triggered = None

    risk_uc = MagicMock(spec=AssessRiskUseCase)
    risk_uc.execute.side_effect = [
        ValueError("no candle data"),  # first ticker fails
        MagicMock(assessment=success_assessment),  # second succeeds
    ]

    c1 = MagicMock()
    c1.ticker = "BBCA"
    c1.fundamentals = None
    c1.bandar_detector = None

    c2 = MagicMock()
    c2.ticker = "TLKM"
    c2.fundamentals = None
    c2.bandar_detector = None

    AccumulationRiskFunnel(risk_uc).run([c1, c2], _TODAY)

    # c1 failed — risk_assessment should not be set (MagicMock auto-creates attribute)
    # Verify execute was called for both
    assert risk_uc.execute.call_count == 2
    # c2 got its assessment
    assert c2.risk_assessment == success_assessment


# ─── to_dict includes risk fields ────────────────────────────────────────────


def test_to_dict_includes_risk_fields_when_assessment_present():
    from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
    from src.domain.value_objects.risk_assessment import RiskAssessment

    snapshot = IndicatorSnapshot(
        date=_TODAY, sma=Decimal("5000"), ema=Decimal("5000"), rsi=Decimal("50")
    )
    assessment = RiskAssessment(
        rationale=("F-score=1 ≤ 3 (distress threshold)",),
        snapshot_date=_TODAY,
        indicators=snapshot,
        gate_triggered="FundamentalGate",
        gate_is_structural=True,
        gate_confidence=100,
    )

    c = AccumulationCandidate(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("10_000_000"),
        consecutive_streak=3,
        foreign_vwap=None,
        current_price=Decimal("5000"),
        vwap_discount_pct=None,
        rsi=45.0,
        trend="UP",
        foreign_flow_score=75.0,
        top_brokers=["AK"],
        institutional_flag=True,
        risk_assessment=assessment,
    )
    d = c.to_dict()
    assert d["risk_status"] == "BLOCKED"
    assert "risk_level" not in d
    assert d["risk_confidence"] == 100
    assert d["risk_gate"] == "FundamentalGate"


def test_to_dict_risk_fields_none_when_no_assessment():
    c = AccumulationCandidate(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("10_000_000"),
        consecutive_streak=3,
        foreign_vwap=None,
        current_price=Decimal("5000"),
        vwap_discount_pct=None,
        rsi=45.0,
        trend="UP",
        foreign_flow_score=75.0,
        top_brokers=None,
        institutional_flag=False,
        risk_assessment=None,
    )
    d = c.to_dict()
    assert d["risk_status"] is None
    assert "risk_level" not in d
    assert d["risk_confidence"] is None
    assert d["risk_gate"] is None
