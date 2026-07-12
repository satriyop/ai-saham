from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli.analyze_swing_display import (
    SwingOutputDisplayContext,
    SwingOutputDisplayOptions,
    print_swing_output,
)
from src.application.dto.swing_analysis import SwingDiagnostics, SwingEvidence, SwingVerdict
from src.application.services.swing_data_freshness import SwingDataFreshness
from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerGroupContribution,
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
)
from src.domain.value_objects.institutional_accumulation_evidence import (
    EvidenceStatus,
)
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence


def _freshness() -> SwingDataFreshness:
    return SwingDataFreshness(
        as_of_date=date(2026, 7, 1),
        candle_start=date(2026, 1, 1),
        candle_end=date(2026, 6, 30),
        broker_start=date(2026, 1, 1),
        broker_end=date(2026, 6, 30),
        warnings=(),
    )


def _minimal_signal_assessment(alpha_trigger_score=None) -> SimpleNamespace:
    strength = SimpleNamespace(value="MODERATE")
    entry_quality = SimpleNamespace(value="WATCH")
    return SimpleNamespace(
        assessment=SimpleNamespace(
            score=65,
            strength=strength,
            entry_quality=entry_quality,
            score_label="65/100",
            confidence_score=0.8,
            rationale=("moderate signal",),
            breakdown_dict={},
            decision_constraints=None,
        ),
        coverage_warning=None,
        active_flags=(),
        flag_adjustment=0,
        raw_group_score=65,
        evidence_confidence=0.8,
        alpha_trigger_score=alpha_trigger_score,
    )


def _production_contribution(group: str = "setup_quality") -> AlphaTriggerGroupContribution:
    return AlphaTriggerGroupContribution(
        group=group,
        score=70.0,
        configured_weight=0.6,
        effective_weight=0.6,
        alpha_fraction=0.7,
        trigger_fraction=0.3,
        alpha_weighted=29.4,
        trigger_weighted=12.6,
        evidence_status=EvidenceAuthorityStatus.PRODUCTION,
        present=True,
        trigger_allowed=True,
        reasons=("good setup",),
    )


def _phase_blocked_flow_contribution() -> AlphaTriggerGroupContribution:
    return AlphaTriggerGroupContribution(
        group="institutional_flow",
        score=95.0,
        configured_weight=0.30,
        effective_weight=0.30,
        alpha_fraction=0.80,
        trigger_fraction=0.20,
        alpha_weighted=22.8,
        trigger_weighted=0.0,
        evidence_status=EvidenceAuthorityStatus.PRODUCTION,
        present=True,
        trigger_allowed=False,
        reasons=("flow_trigger_blocked:setup_phase_not_breakout_confirmation",),
    )


def _diagnostic_contribution(group: str = "sector_context") -> AlphaTriggerGroupContribution:
    return AlphaTriggerGroupContribution(
        group=group,
        score=50.0,
        configured_weight=0.3,
        effective_weight=0.0,
        alpha_fraction=0.7,
        trigger_fraction=0.3,
        alpha_weighted=0.0,
        trigger_weighted=0.0,
        evidence_status=EvidenceAuthorityStatus.DIAGNOSTIC,
        present=True,
        trigger_allowed=False,
        reasons=("diagnostic only",),
    )


def _alpha_trigger_score(
    *,
    with_production: bool = True,
    with_diagnostic: bool = False,
    with_unavailable: bool = False,
) -> AlphaTriggerScore:
    contribs = []
    if with_production:
        contribs.append(_production_contribution())
    if with_diagnostic:
        contribs.append(_diagnostic_contribution())
    return AlphaTriggerScore(
        alpha_score=62.0 if not with_unavailable else None,
        trigger_score=55.0 if not with_unavailable else None,
        final_exact_score=59.5 if not with_unavailable else None,
        horizon="swing_7d",
        alpha_weight=0.7,
        group_contributions=tuple(contribs),
        coverage=0.75,
        authority_coverage=0.6,
        conviction=0.65,
        flow_trigger_allowed=True,
        reasons=("within threshold",),
        unavailable_reasons=("sector_context missing",) if with_unavailable else (),
    )


def _sector_context_evidence_full() -> SectorContextEvidence:
    return SectorContextEvidence(
        sector="Finance",
        peer_count=3,
        peer_tickers=("BBNI", "BBRI", "BMRI"),
        sector_20d_return=0.032,
        sector_vs_ihsg_20d=0.011,
        sector_breadth=0.667,
        ticker_vs_sector_rs=0.015,
        sector_regime="BULLISH",
        coverage_score=0.75,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("sector bullish",),
        unavailable_reasons=(),
    )


def _sector_context_unavailable() -> SectorContextEvidence:
    return SectorContextEvidence.unavailable(reason="no peer candles available")


def _call_print(
    *,
    include_signal_detail: bool = False,
    include_market_detail: bool = False,
    include_flow_detail: bool = False,
    signal_assessment=None,
    sector_context_evidence=None,
    institutional_accumulation_evidence=None,
) -> None:
    ctx = SwingOutputDisplayContext(
        ticker="BBCA",
        today=date(2026, 7, 1),
        strategy_name="foreign-accumulation",
        window=7,
        verdict=SwingVerdict(
            trade_setup=None,
            signal_assessment=signal_assessment,
            risk_response=None,
            market_regime=None,
        ),
        evidence=SwingEvidence(
            accumulation_candidate=None,
            setup_eval=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
            sector_context_evidence=sector_context_evidence,
            institutional_accumulation_evidence=institutional_accumulation_evidence,
        ),
        diagnostics=SwingDiagnostics(
            data_freshness=_freshness(),
            flow_detail=None,
            broker_detail=None,
            broker_quality_note=None,
            refresh_actions=(),
        ),
        options=SwingOutputDisplayOptions(
            include_strategy=False,
            include_sentiment=False,
            include_flow_detail=include_flow_detail,
            include_signal_detail=include_signal_detail,
            include_risk_detail=False,
            include_market_detail=include_market_detail,
        ),
    )
    print_swing_output(ctx)
