from datetime import date, timedelta
from decimal import Decimal

from src.application.services.setup_phase_detector import (
    SetupPhaseConfig,
    SetupPhaseDetector,
    SetupPhaseRequirementConfig,
    VolumeTriggerValidityConfig,
    _volume_trigger_evidence,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
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
    """Build 21 candles with a genuine dry-up-then-expansion volume pattern.

    With defaults (dry_up_lookback_sessions=5, dry_up_reference_sessions=20),
    total_required = dry_up_reference_sessions + 1 = 21:
      - indices 0-14 (15 candles, reference window): volume=2_000 (baseline)
      - indices 15-19 (5 candles, dry-up window): volume=800
        -> dry_up_ratio = 800/2000 = 0.4 <= dry_up_max_ratio(0.50) confirmed
      - index 20 (latest/today): volume=1_600
        -> expansion_ratio = 1600/800 = 2.0 >= expansion_min_ratio(1.50) confirmed
    """
    start = date(2026, 6, 1)
    rows = []
    for idx in range(21):
        close = Decimal("100")
        high = Decimal("101")
        open_ = Decimal("99")
        if idx < 15:
            volume = 2_000
        elif idx < 20:
            volume = 800
        else:
            volume = 1_600
        if breakout and idx == 20:
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
        SetupGate("accum_score", flow, "70", ">= 60"),
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


def _excess_return(window_sessions: int, excess_return_pct: float) -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=window_sessions,
        ticker_return_pct=excess_return_pct,
        benchmark_return_pct=0.0,
        excess_return_pct=excess_return_pct,
        window_start=date(2026, 6, 1),
        window_end=date(2026, 6, 20),
        common_session_count=window_sessions + 1,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
        unavailable_reason=None,
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
        "benchmark_excess_return_5_session": _excess_return(5, 2.0),
        "benchmark_excess_return_20_session": _excess_return(20, 2.0),
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
    assert any(
        "volume dry-up then expansion confirmed" in reason
        for reason in snapshot.reasons
    )
    assert snapshot.volume_dry_up_confirmed is True
    assert snapshot.volume_expansion_confirmed is True
    assert snapshot.volume_trigger_confirmed is True
    assert snapshot.volume_dry_up_ratio == 0.4
    assert snapshot.volume_expansion_ratio == 2.0


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
    assert any(
        "synthetic/missing source" in reason
        for reason in snapshot.unavailable_evidence_reasons
    )


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

    assert snapshot.phase_input_coverage < 1.0
    assert any(
        "synthetic/missing source" in reason
        for reason in snapshot.unavailable_evidence_reasons
    )


def test_negative_benchmark_excess_return_emits_no_reasons():
    """A deeply negative benchmark excess return is DIAGNOSTIC_UNVALIDATED and
    must not surface any rs_policy-shaped constraint reason — the production
    authority path was removed in Task HIGH-1."""
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(
            benchmark_excess_return_5_session=_excess_return(5, -50.0),
            benchmark_excess_return_20_session=_excess_return(20, -50.0),
        ),
        flow_evidence=None,
        setup_family="foreign-bounce",
    )

    assert not any("rs_policy" in reason for reason in snapshot.reasons)
    assert not any("rs_vs_ihsg" in reason for reason in snapshot.reasons)


def test_injected_config_drives_sequence_validity_for_custom_family():
    """Config-driven dispatch mechanism: a setup_family unknown to the default
    SetupPhaseConfig still gets sequence validation when an explicit config
    with a matching requirements_by_family entry is injected."""
    custom_cfg = SetupPhaseConfig(
        requirements_by_family={
            "my-custom-setup": SetupPhaseRequirementConfig(
                required_sequence=(
                    SetupPhaseState.COMPRESSION,
                    SetupPhaseState.BREAKOUT_CONFIRMATION,
                ),
            ),
        }
    )

    valid_snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="my-custom-setup",
        previous_phases=(SetupPhaseState.COMPRESSION,),
        config=custom_cfg,
    )

    assert valid_snapshot.sequence_valid is True

    invalid_snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="my-custom-setup",
        previous_phases=(),
        config=custom_cfg,
    )

    assert invalid_snapshot.sequence_valid is False


def test_pullback_family_sequence_valid_requires_vwap_reclaim_reason():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="pullback-continuation",
    )

    assert snapshot.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert any("VWAP reclaim" in reason for reason in snapshot.reasons)
    assert snapshot.sequence_valid is True


def test_pullback_family_sequence_invalid_without_vwap_reclaim_reason():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(vwap_pct=None),
        flow_evidence=_flow(),
        setup_family="pullback-continuation",
    )

    # Without vwap_pct, the "VWAP reclaim" price gate is not constructed, but
    # breakout is still reached via "positive close above previous high" and
    # "positive close" alone — neither of which counts as a reclaim/pivot
    # confirmation, so sequence_valid must be False (not None).
    assert not any("VWAP reclaim" in reason for reason in snapshot.reasons)
    assert snapshot.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert snapshot.sequence_valid is False


def test_confirmation_family_has_no_sequence_requirement():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="smart-money-confirmed",
    )

    assert snapshot.sequence_valid is None


def test_unknown_family_has_no_sequence_requirement():
    snapshot = SetupPhaseDetector().detect(
        candles=_candles(breakout=True),
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="totally-unrecognized-setup-xyz",
    )

    assert snapshot.sequence_valid is None


def _candles_with_volumes(
    volumes: list[int],
    *,
    latest_open: Decimal = Decimal("99"),
    latest_close: Decimal = Decimal("100"),
) -> list[Candle]:
    """Build len(volumes) candles with a fixed non-breakout price shape, except
    the final (latest) candle's open/close are overridable so tests can flip
    the positive-close gate independently of the volume pattern."""
    start = date(2026, 6, 1)
    rows = []
    n = len(volumes)
    for idx, volume in enumerate(volumes):
        close = Decimal("100")
        high = Decimal("101")
        open_ = Decimal("99")
        if idx == n - 1:
            open_ = latest_open
            close = latest_close
            high = max(high, latest_close + Decimal("1"))
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


def test_expansion_without_dry_up_does_not_confirm_breakout():
    """Dry-up window is NOT meaningfully lower than the reference window
    (ratio=1.0, not <=0.50), but the latest session spikes well above the
    dry-up window average (expansion_ratio=2.0 >= 1.50), with a positive
    close so price gates pass. Must NOT reach BREAKOUT_CONFIRMATION and must
    not claim the confirmed trigger."""
    volumes = [1_000] * 20 + [2_000]
    candles = _candles_with_volumes(
        volumes, latest_open=Decimal("101"), latest_close=Decimal("105")
    )
    snapshot = SetupPhaseDetector().detect(
        candles=candles,
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert snapshot.current_phase != SetupPhaseState.BREAKOUT_CONFIRMATION
    assert "breakout: volume expansion without prior dry-up" in snapshot.reasons
    assert not any(
        "volume dry-up then expansion confirmed" in reason
        for reason in snapshot.reasons
    )


def test_dry_up_without_expansion_routes_to_compression():
    """Dry-up IS confirmed (dry-up window notably lower than reference,
    ratio=0.4) but the latest session does NOT spike (expansion_ratio=1.125,
    not >=1.50). Default _setup_evidence() bb_width_pctile=0.15 lands the
    phase on COMPRESSION."""
    volumes = [2_000] * 15 + [800] * 5 + [900]
    candles = _candles_with_volumes(volumes)
    snapshot = SetupPhaseDetector().detect(
        candles=candles,
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert snapshot.current_phase == SetupPhaseState.COMPRESSION
    assert (
        "compression: volume dry-up readiness, no expansion yet"
        in snapshot.reasons
    )


def test_volume_trigger_evidence_insufficient_sessions_marks_data_invalid():
    candles = _candles(breakout=True)[:15]
    evidence = _volume_trigger_evidence(
        candles,
        setup_evidence=_setup_evidence(),
        cfg=VolumeTriggerValidityConfig(),
    )

    assert evidence.data_valid is False
    assert any(
        "required 21 sessions" in reason for reason in evidence.unavailable_reasons
    )


def test_detect_reports_partial_coverage_with_fewer_than_20_candles():
    candles = _candles(breakout=True)[:15]
    snapshot = SetupPhaseDetector().detect(
        candles=candles,
        setup_eval=_setup_eval(),
        setup_evidence=_setup_evidence(),
        flow_evidence=_flow(),
        setup_family="foreign-bounce",
    )

    assert snapshot.phase_input_coverage < 1.0


def test_volume_trigger_evidence_zero_volume_distortion_above_tolerance():
    candles = _candles(zero_volume=True)
    evidence = _volume_trigger_evidence(
        candles,
        setup_evidence=_setup_evidence(candle_source="stockbit"),
        cfg=VolumeTriggerValidityConfig(),
    )

    assert evidence.data_valid is False
    assert (
        "volume trigger unavailable: insufficient valid 20d volume sessions"
        in evidence.unavailable_reasons
    )


def test_expansion_requires_positive_close_blocks_on_flat_or_negative_close():
    volumes = [2_000] * 15 + [800] * 5 + [1_600]
    candles = _candles_with_volumes(
        volumes, latest_open=Decimal("100"), latest_close=Decimal("99")
    )

    blocked = _volume_trigger_evidence(
        candles,
        setup_evidence=_setup_evidence(),
        cfg=VolumeTriggerValidityConfig(expansion_requires_positive_close=True),
    )
    assert blocked.expansion_confirmed is False
    assert blocked.volume_trigger_confirmed is False
    # Raw ratio math is unaffected by the close gate.
    assert blocked.expansion_ratio == 2.0
    assert blocked.dry_up_confirmed is True

    allowed = _volume_trigger_evidence(
        candles,
        setup_evidence=_setup_evidence(),
        cfg=VolumeTriggerValidityConfig(expansion_requires_positive_close=False),
    )
    assert allowed.expansion_confirmed is True
    assert allowed.volume_trigger_confirmed is True
