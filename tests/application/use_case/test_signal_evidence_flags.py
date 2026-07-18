"""Flag and penalty tests for signal evidence use case."""


from src.application.use_case.assess_signal_use_case import (
    AnalystBearishFlagConfig,
    InsiderSellingFlagConfig,
    SignalEngineConfig,
    SignalFlagsConfig,
    ValuationStretchedFlagConfig,
)
from src.domain.value_objects.signal_assessment import SignalStrength
from tests.application.use_case.signal_evidence_fixtures import (
    _ctx,
    _req,
    _setup_evidence,
    _use_case,
    _flow_evidence,
)


def test_valuation_stretched_flag_applies_penalty():
    uc = _use_case()
    ctx = _ctx(forward_pe=55.0)   # > 50.0 threshold
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "VALUATION_STRETCHED" in resp.active_flags
    assert resp.flag_adjustment == -10
    assert resp.assessment.score == 40   # 50 - 10


def test_valuation_stretched_not_triggered_at_threshold():
    uc = _use_case()
    ctx = _ctx(forward_pe=50.0)   # == threshold → NOT triggered (strictly >)
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "VALUATION_STRETCHED" not in resp.active_flags


def test_valuation_stretched_not_triggered_below_threshold():
    uc = _use_case()
    ctx = _ctx(forward_pe=30.0)
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "VALUATION_STRETCHED" not in resp.active_flags


def test_analyst_bearish_flag_applies_penalty():
    uc = _use_case()
    ctx = _ctx(analyst_buy_pct=0.10)   # < 0.20 threshold
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "ANALYST_BEARISH" in resp.active_flags
    assert resp.flag_adjustment == -8
    assert resp.assessment.score == 42   # 50 - 8


def test_analyst_bearish_not_triggered_at_threshold():
    uc = _use_case()
    ctx = _ctx(analyst_buy_pct=0.20)   # == threshold → NOT triggered (strictly <)
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "ANALYST_BEARISH" not in resp.active_flags


def test_insider_selling_flag_applies_penalty():
    uc = _use_case()
    ctx = _ctx(insider_net_buy_ratio=-0.50)   # < -0.30 threshold
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "INSIDER_SELLING" in resp.active_flags
    assert resp.flag_adjustment == -12
    assert resp.assessment.score == 38   # 50 - 12


def test_insider_selling_not_triggered_at_threshold():
    uc = _use_case()
    ctx = _ctx(insider_net_buy_ratio=-0.30)   # == threshold → NOT triggered (strictly <)
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "INSIDER_SELLING" not in resp.active_flags


def test_neutral_insider_does_not_trigger_flag():
    uc = _use_case()
    ctx = _ctx(insider_net_buy_ratio=0.0)
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "INSIDER_SELLING" not in resp.active_flags


def test_multiple_flags_stack():
    uc = _use_case()
    ctx = _ctx(
        forward_pe=60.0,           # VALUATION_STRETCHED → -10
        analyst_buy_pct=0.05,      # ANALYST_BEARISH → -8
        insider_net_buy_ratio=-0.60,  # INSIDER_SELLING → -12
    )
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "VALUATION_STRETCHED" in resp.active_flags
    assert "ANALYST_BEARISH" in resp.active_flags
    assert "INSIDER_SELLING" in resp.active_flags
    assert resp.flag_adjustment == -30
    # 50 - 30 = 20 → WEAK
    assert resp.assessment.score == 20
    assert resp.assessment.strength == SignalStrength.WEAK


def test_score_clamped_at_zero_with_multiple_flags():
    uc = _use_case()
    ctx = _ctx(
        forward_pe=60.0,
        analyst_buy_pct=0.05,
        insider_net_buy_ratio=-0.60,
    )
    resp = uc.execute(_req(setup_evidence=_setup_evidence("NO_MATCH"), signal_context=ctx))
    assert resp.assessment.score == 0
    assert resp.assessment.score >= 0


def test_custom_flag_threshold_changes_trigger_point():
    cfg = SignalEngineConfig(
        flags=SignalFlagsConfig(
            valuation_stretched=ValuationStretchedFlagConfig(
                enabled=True,
                forward_pe_threshold=30.0,   # tighter threshold
                score_penalty=5,
            ),
            analyst_bearish=AnalystBearishFlagConfig(),
            insider_selling=InsiderSellingFlagConfig(),
        )
    )
    uc = _use_case(cfg)
    ctx = _ctx(forward_pe=35.0)   # > 30.0 → fires with custom config
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "VALUATION_STRETCHED" in resp.active_flags
    assert resp.flag_adjustment == -5


def test_disabled_flag_does_not_apply():
    cfg = SignalEngineConfig(
        flags=SignalFlagsConfig(
            valuation_stretched=ValuationStretchedFlagConfig(enabled=False),
            analyst_bearish=AnalystBearishFlagConfig(),
            insider_selling=InsiderSellingFlagConfig(),
        )
    )
    uc = _use_case(cfg)
    ctx = _ctx(forward_pe=999.0)   # way above threshold but flag disabled
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert "VALUATION_STRETCHED" not in resp.active_flags
