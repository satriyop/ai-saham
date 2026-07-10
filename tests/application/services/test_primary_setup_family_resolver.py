"""Tests for PrimarySetupFamilyResolver's deterministic priority cascade.

Covers the "Setup Family Source Contract" priority order documented in the
resolver's own docstring:
  1. explicit_request
  2. strategy_evidence (only when the strategy actually MATCHED)
  3. detected_screen_evidence / detected_unranked (named swing setups)
  4. fallback_unknown
"""

from datetime import date
from decimal import Decimal

from src.application.services.primary_setup_family_resolver import (
    PrimarySetupFamilyResolver,
)
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.use_case.evaluate_swing_setup_use_case import (
    CoiledSpringSetupConfig,
    ForeignBounceSetupConfig,
    PullbackContinuationSetupConfig,
    SmartMoneyConfirmedSetupConfig,
    SwingSetupCatalogConfig,
)
from src.domain.value_objects.strategy_evidence import (
    StrategyEvidence,
    StrategyEvidenceOutcome,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _candidate(**kwargs) -> AccumulationCandidate:
    defaults = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("9000"),
        current_price=Decimal("8640"),
        vwap_discount_pct=4.0,
        rsi=45.0,
        trend="SIDE",
        foreign_flow_score=80.0,
        top_brokers=["AK", "BK"],
        institutional_flag=True,
        avg_flow_ratio=6.0,
    )
    defaults.update(kwargs)
    return AccumulationCandidate(**defaults)


def _strategy_evidence(**kwargs) -> StrategyEvidence:
    defaults = dict(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 9),
        strategy_name="foreign-accumulation",
        outcome=StrategyEvidenceOutcome.MATCHED,
    )
    defaults.update(kwargs)
    return StrategyEvidence(**defaults)


# ── 1. explicit request wins outright ───────────────────────────────────────

def test_explicit_request_wins_outright():
    resolver = PrimarySetupFamilyResolver()

    result = resolver.resolve(candidate=None, request_setup_family="foreign-bounce")

    assert result.primary_setup_family == "foreign_bounce"
    assert result.matched_setup_families == ("foreign_bounce",)
    assert result.setup_family_source == "explicit_request"


# ── 2. strategy evidence wins over a conflicting detected family ───────────

def test_strategy_evidence_wins_over_conflicting_detected_family():
    resolver = PrimarySetupFamilyResolver()

    # Candidate MATCHes coiled-spring (family "breakout") via loose gates; the
    # remaining swing setups are disabled so only coiled-spring can match.
    candidate = _candidate(
        foreign_flow_score=62.0,
        bb_width_pctile=0.12,
        avg_flow_ratio=3.5,
        rsi=58.0,
    )
    catalog = SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(
            gate_max_bb_width_pctile=0.20, family="breakout"
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=False, family="pullback"
        ),
    )
    strategy_evidence = _strategy_evidence(strategy_name="foreign-accumulation")

    result = resolver.resolve(
        candidate=candidate,
        strategy_evidence=strategy_evidence,
        swing_setup_catalog=catalog,
    )

    assert result.primary_setup_family == "foreign_bounce"
    assert result.setup_family_source == "strategy_evidence"
    assert "foreign_bounce" in result.matched_setup_families
    assert "breakout" in result.matched_setup_families
    # strategy-proposed family ordered first
    assert result.matched_setup_families[0] == "foreign_bounce"


# ── 3. multiple detected families -> deterministic primary via priority ────

def test_multiple_detected_families_select_deterministic_primary_via_priority():
    resolver = PrimarySetupFamilyResolver()

    # Candidate MATCHes both coiled-spring (family "breakout") and
    # pullback-continuation (family "pullback"). foreign-bounce and
    # smart-money-confirmed are disabled so they cannot also match.
    candidate = _candidate(
        foreign_flow_score=70.0,
        bb_width_pctile=0.12,
        avg_flow_ratio=6.0,
        rsi=55.0,
        trend="UP",
        vwap_discount_pct=1.0,
    )
    catalog = SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(
            gate_max_bb_width_pctile=0.20, family="breakout"
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            gate_required_trend="UP",
            gate_min_vwap_discount_pct=-2.0,
            gate_min_rsi=40.0,
            gate_max_rsi=65.0,
            family="pullback",
        ),
    )

    result = resolver.resolve(candidate=candidate, swing_setup_catalog=catalog)

    assert result.primary_setup_family == "breakout"
    assert result.setup_family_source == "detected_screen_evidence"
    assert "breakout" in result.matched_setup_families
    assert "pullback" in result.matched_setup_families


# ── 4. no matched family -> conservative fallback ──────────────────────────

def test_no_matched_family_falls_back_conservatively():
    resolver = PrimarySetupFamilyResolver()

    # Every named setup is disabled -> guaranteed NO_MATCH for all of them.
    candidate = _candidate()
    catalog = SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(enabled=False, family="breakout"),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=False, family="pullback"
        ),
    )

    result = resolver.resolve(candidate=candidate, swing_setup_catalog=catalog)

    assert result.matched_setup_families == ()
    assert result.primary_setup_family is None
    assert result.setup_family_source == "fallback_unknown"


# ── 5. detected family outside the priority tuple -> unranked ─────────────

def test_detected_family_outside_priority_tuple_is_unranked():
    # smart-money-confirmed can never MATCH via this resolver because
    # _from_screen_evidence calls EvaluateSwingSetupUseCase without a
    # broker_detail, so we instead force the "matched but unranked" branch by
    # supplying a priority tuple that excludes the family the candidate
    # actually matches (coiled-spring -> "breakout").
    resolver = PrimarySetupFamilyResolver(priority=())

    candidate = _candidate(
        foreign_flow_score=62.0,
        bb_width_pctile=0.12,
        avg_flow_ratio=3.5,
        rsi=58.0,
    )
    catalog = SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(
            gate_max_bb_width_pctile=0.20, family="breakout"
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=False, family="pullback"
        ),
    )

    result = resolver.resolve(candidate=candidate, swing_setup_catalog=catalog)

    assert result.primary_setup_family is None
    assert result.setup_family_source == "detected_unranked"
    assert "breakout" in result.matched_setup_families
