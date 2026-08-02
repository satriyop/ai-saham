"""Unit tests for AccumulationScreenHardFilterPolicy resolution."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
    resolve_accumulation_screen_hard_filter_policy,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)


def _swing(*, market_cap: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        min_market_cap_idr=market_cap,
        tier1_broker_codes=frozenset({"AK"}),
        bci_cluster_min_count=3,
        bci_stable_min_count=1,
        resistance_gate_enabled=False,
        resistance_headroom_min_pct=0.0,
        ex_date_warning_days=0,
    )


def _screener(
    *,
    accum_enabled: bool = True,
    accum_value: float = 0.0,
    signal_enabled: bool = False,
    signal_value: float = 45.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        min_accum_score=SimpleNamespace(enabled=accum_enabled, value=accum_value),
        min_signal_score=SimpleNamespace(enabled=signal_enabled, value=signal_value),
    )


def test_default_production_hard_filters() -> None:
    policy = resolve_accumulation_screen_hard_filter_policy(
        swing_policy=_swing(),
        accumulation_screener_config=_screener(),
    )
    assert policy == AccumulationScreenHardFilterPolicy(
        min_market_cap_idr=0,
        min_piotroski=0,
        min_accum_score=0.0,
        min_accum_score_enabled=True,
        min_signal_score=45.0,
        min_signal_score_enabled=False,
    )
    assert policy.market_cap_enabled is False
    assert policy.piotroski_enabled is False


def test_market_cap_from_swing_policy_not_second_parse() -> None:
    policy = resolve_accumulation_screen_hard_filter_policy(
        swing_policy=_swing(market_cap=500_000_000_000),
        accumulation_screener_config=_screener(),
    )
    assert policy.min_market_cap_idr == 500_000_000_000
    assert policy.market_cap_enabled is True


def test_capture_neutralization_does_not_mutate_policy_object() -> None:
    policy = resolve_accumulation_screen_hard_filter_policy(
        swing_policy=_swing(),
        accumulation_screener_config=_screener(),
    )
    request = BuildSignalObservationScreenRequest.from_configs(
        swing_policy=_swing(),
        accumulation_screener_config=_screener(),
        min_net_buy_days=1,
        hard_filter_policy=policy,
        disable_score_filters=True,
    )
    assert request.min_accum_score_enabled is False
    assert request.min_signal_score_enabled is False
    assert policy.min_accum_score_enabled is True
    assert policy.min_signal_score_enabled is False
    assert policy.min_signal_score == 45.0


def test_hard_filter_policy_rejects_combined_overrides() -> None:
    policy = resolve_accumulation_screen_hard_filter_policy(
        swing_policy=_swing(),
        accumulation_screener_config=_screener(),
    )
    with pytest.raises(ValueError, match="cannot be combined"):
        BuildSignalObservationScreenRequest.from_configs(
            swing_policy=_swing(),
            accumulation_screener_config=_screener(),
            min_net_buy_days=1,
            hard_filter_policy=policy,
            min_piotroski=5,
        )
