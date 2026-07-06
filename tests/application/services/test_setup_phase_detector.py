from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.setup_phase_detector import SetupPhaseDetector
from src.domain.entities.candle import Candle
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
)
from src.domain.value_objects.setup_evaluation import (
    SetupEvaluation,
    SetupGate,
    SetupMatch,
)
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.setup_phase import SetupPhaseState


def _candles(*, breakout: bool = False, zero_volume: bool = False) -> list[Candle]:
    start = date(2026, 6, 1)
    rows = []
    for idx in range(20):
        close = Decimal("100")
        high = Decimal("101")
        open_ = Decimal("99")
        volume = 1_000
        if idx >= 15:
            volume = 2_000
        if breakout and idx == 19:
            open_ = Decimal("101")
            close = Decimal("105")
            high = Decimal("106")
        if zero_volume and idx in {3, 7, 11}:
            volume = 0
        rows.append(
            Candle(
                ticker="BBCA",
                date=start + timedelta(days=idx),
                open=open_,
                high=high,
                low=Decimal("98"),
                close=close,
                volume=volume,
            )
        )
    return rows


def _setup_eval(*, flow=True, bb=True) -> SetupEvaluation:
    gates = (
        SetupGate("foreign_flow_score", flow, "70", ">= 60"),
        SetupGate("flow_pct", flow, "5%", ">= 2%"),
        SetupGate("bb_width_pctile", bb, "0.15", "<= 0.20"),
    )
    return SetupEvaluation(
        name="foreign-bounce",
        match=SetupMatch.MATCH if flow and bb else SetupMatch.PARTIAL,
        gates=gates,
        failed_reasons=tuple(
            f"{gate.label}: {gate.actual} (required {gate.required})"
            for gate in gates
            if not gate.passed
        ),
    )


def _setup_evidence(**overrides) -> SetupEvidence:
    values = {
        "ticker": "BBCA",
        "snapshot_date": date(2026, 6, 20),
        "setup_name": "foreign-bounce",
        "setup_match": "MATCH",
        "match_strength": 100.0,
        "failed_gates": (),
        "trend": "SIDE",
        "rsi": 55.0,
        "bb_width_pctile": 0.15,
        "vwap_discount_pct": 3.0,
        "vwap_pct": 1.0,
        "rs_vs_ihsg_5d": 2.0,
        "rs_freshness": Freshness.FRESH,
        "volume_trend_ratio": 1.5,
        "volume_freshness": Freshness.FRESH,
        "candle_source": "stockbit",
    }
    values.update(overrides)
    return SetupEvidence(**values)


def _flow(**overrides) -> FlowConfirmationEvidence:
    values = {
        "ticker": "BBCA",
        "snapshot_date": date(2026, 6, 20),
        "flow_signals": (),
        "flow_score_ex_bb": 0.0,
        "confirmation_status": "CONFIRMED",
        "flow_direction": "POSITIVE",
        "bandar_broad_score": 2,
        "bandar_direction": Direction.BULLISH,
        "bandar_freshness": Freshness.FRESH,
        "bci_label": None,
        "bci_tier1_count": 0,
        "uncapped_strength": 0.7,
        "capped_strength": 0.7,
        "group_cap": 0.8,
        "group_freshness": Freshness.FRESH,
    }
    values.update(overrides)
    return FlowConfirmationEvidence(**values)


def test_detector_routes_bb_width_to_compression_not_breakout():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(vwap_pct=-1.0, candle_source="yahoo_inferred"),
        flow_evidence=None,
        setup_family="coiled-spring",
    )

    assert snapshot.current_phase == SetupPhaseState.COMPRESSION
    assert any("BB width" in reason for reason in snapshot.reasons)


def test_detector_routes_close_reclaim_and_valid_volume_to_breakout():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert snapshot.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert snapshot.sequence_valid is False
    assert snapshot.previous_phase is None
    assert any("volume dry-up then expansion" in reason for reason in snapshot.reasons)


def test_breakout_sequence_valid_requires_observed_prior_phases():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
        previous_phases=(
            SetupPhaseState.ACCUMULATION,
            SetupPhaseState.COMPRESSION,
        ),
    )

    assert snapshot.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert snapshot.previous_phase == SetupPhaseState.COMPRESSION
    assert snapshot.sequence_valid is True
    assert [entry.phase for entry in snapshot.history] == [
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
    ]


def test_flow_confirmation_without_volume_cannot_create_breakout():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(candle_source="yahoo_inferred"),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert snapshot.current_phase != SetupPhaseState.BREAKOUT_CONFIRMATION
    assert any("synthetic/missing source" in reason for reason in snapshot.unavailable_evidence_reasons)


def test_terminal_distribution_precedes_constructive_breakout():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(flow_direction="NEGATIVE", bandar_broad_score=-8),
        setup_family="foreign-bounce",
    )

    assert snapshot.current_phase == SetupPhaseState.DISTRIBUTION


def test_failed_gate_preserves_individual_gate_outcomes():
    setup_eval = _setup_eval(flow=False, bb=True)
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(),
        setup_eval=setup_eval,
        setup_evidence=_setup_evidence(
            setup_match="PARTIAL",
            match_strength=60.0,
            candle_source="yahoo_inferred",
            vwap_pct=-1.0,
        ),
        flow_evidence=None,
        setup_family="foreign-bounce",
    )

    assert snapshot.current_phase == SetupPhaseState.COMPRESSION
    assert [gate.passed for gate in setup_eval.gates] == [False, False, True]


def test_volume_trigger_accepts_stock_without_stockbit_source_when_quality_passes():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(candle_source=None),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert snapshot.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert not snapshot.unavailable_evidence_reasons


def test_benchmark_volume_requires_explicit_trusted_source():
    ihsg_candles = [
        Candle(
            ticker="IHSG",
            date=candle.date,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )
        for candle in _candles(breakout=True)
    ]

    missing_source = SetupPhaseDetector().detect(
        candles=ihsg_candles,
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(ticker="IHSG", candle_source=None),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )
    trusted_source = SetupPhaseDetector().detect(
        candles=ihsg_candles,
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(ticker="IHSG", candle_source="stockbit"),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert missing_source.current_phase != SetupPhaseState.BREAKOUT_CONFIRMATION
    assert any("benchmark source missing" in r for r in missing_source.unavailable_evidence_reasons)
    assert trusted_source.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION


def test_volume_trigger_unavailable_for_synthetic_source_or_zero_volume_window():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(zero_volume=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(candle_source="yahoo_inferred"),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert snapshot.coverage_score < 1.0
    assert any("synthetic/missing source" in reason for reason in snapshot.unavailable_evidence_reasons)


def test_negative_rs_emits_decision_constraint_reason():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(rs_vs_ihsg_5d=-5.0),
        flow_evidence=None,
        setup_family="foreign-bounce",
    )

    assert any("rs_policy_hard_exclude" in reason for reason in snapshot.reasons)
