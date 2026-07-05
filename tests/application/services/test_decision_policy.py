from __future__ import annotations

from datetime import date

from src.application.services.decision_policy import DecisionPolicyService
from src.application.use_case.assess_signal_use_case import DecisionPolicyConfig
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.signal_assessment import EntryQuality


SNAP = date(2026, 7, 5)


def _mctx(regime: str) -> MarketContext:
    return MarketContext(
        regime=MarketRegime(regime),
        conviction=0.70,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=SNAP,
    )


def _resolve(
    regime: str,
    *,
    setup_family: str | None = None,
    coverage: float = 1.0,
    conviction: float = 1.0,
):
    return DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=75,
        coverage_score=coverage,
        conviction_score=conviction,
        market_context=_mctx(regime),
        setup_family=setup_family,
    )


def test_risk_on_permits_enter_when_score_and_evidence_floors_pass():
    result = _resolve("RISK_ON")

    assert result.entry_quality == EntryQuality.ENTER
    assert result.constraints.max_decision == "ENTER"
    assert result.constraints.regime_enter_allowed is True
    assert result.constraints.effective_size_multiplier == 1.0


def test_neutral_can_permit_enter_with_reduced_size():
    result = _resolve("NEUTRAL")

    assert result.entry_quality == EntryQuality.ENTER
    assert result.constraints.max_decision == "ENTER"
    assert result.constraints.regime_enter_allowed is True
    assert result.constraints.effective_size_multiplier == 0.50


def test_risk_off_blocks_enter_even_when_entry_quality_is_enter():
    result = _resolve("RISK_OFF", coverage=0.0, conviction=0.0)

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
    assert result.constraints.regime_enter_allowed is False
    assert "RISK_OFF disables ENTER" in result.constraints.constraint_reasons


def test_volatile_blocks_enter():
    result = _resolve("VOLATILE")

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
    assert result.constraints.regime_enter_allowed is False
    assert result.constraints.effective_size_multiplier == 0.0


def test_setup_specific_policy_cannot_reenable_enter_under_risk_off():
    config = DecisionPolicyConfig(
        setup_regime_policy={
            "foreign_bounce": {
                "RISK_OFF": "allowed_if_flow_confirmation_strong",
            },
        },
    )

    result = DecisionPolicyService(config).resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        coverage_score=1.0,
        conviction_score=1.0,
        market_context=_mctx("RISK_OFF"),
        setup_family="foreign-bounce",
    )

    assert result.entry_quality == EntryQuality.WATCH
    assert result.constraints.max_decision == "WATCH"
    assert result.constraints.setup_family == "foreign_bounce"
    assert result.constraints.setup_regime_action == "allowed_if_flow_confirmation_strong"
    assert (
        "Setup-specific policy cannot override regime ENTER block"
        in result.constraints.constraint_reasons
    )
