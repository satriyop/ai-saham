"""`risk_engine.gates.unevaluable_policy` — behaviour of each policy value.

The default (`surface`) must leave the aggregate verdict exactly as it was
before the key existed: an unevaluable gate is recorded, never blocks, and
never becomes a pass. `block` is the explicit opt-in that makes an unknown a
reject; it is proven here so switching it is a reviewed decision, not a
surprise.

Invariance of the *action* distribution under the default is proven separately
and independently by the frozen ADR-068 behavioural output digest, which hashes
`action`, `blocking_gates`, `risk_gate_triggered` and every per-gate `outcome`
across the whole probe set (tests/application/services/test_behavioral_probe_*).
This module proves the complementary half: that the digest's stability is not
vacuous, because the policy demonstrably *can* move the verdict.

Layer: Application
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_unevaluable_gate_policy,
)
from src.application.use_case.assess_risk_use_case import (
    AssessRiskRequest,
    AssessRiskUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.risk_gate import (
    GateContext,
    UnevaluableGateAction,
    UnevaluableGatePolicy,
)
from src.infrastructure.config.engine_config_loader import load_engine_config

_TODAY = date(2026, 6, 23)
_1T = 1_000_000_000_000
_SURFACE = UnevaluableGatePolicy()
_BLOCK = UnevaluableGatePolicy(action=UnevaluableGateAction.BLOCK, block_confidence=50)


class _Repo(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def get_candles(self, ticker: str, start_date=None, end_date=None) -> list[Candle]:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date:
            rows = [c for c in rows if c.date >= start_date]
        if end_date:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker, start_date, end_date):
        return bool(self.get_candles(ticker, start_date, end_date))

    def get_date_range(self, ticker):
        rows = self.get_candles(ticker)
        return (rows[0].date, rows[-1].date) if rows else None

    def list_tickers_with_candles_between(self, start_date, end_date):
        return []


def _candles(count: int = 365) -> list[Candle]:
    price = Decimal("5000")
    return [
        Candle(
            ticker="BBCA",
            date=_TODAY - timedelta(days=count - i),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=2_000_000,
        )
        for i in range(count)
    ]


def _use_case(policy, structural=None, execution=None) -> AssessRiskUseCase:
    return AssessRiskUseCase(
        repository=_Repo(_candles()),
        structural_gates=structural if structural is not None else [FundamentalGate()],
        execution_gates=execution,
        unevaluable_gate_policy=policy,
    )


def _ctx(**overrides) -> GateContext:
    base = {
        "piotroski_f_score": 7,
        "market_cap_idr": 2 * _1T,
        "free_float_pct": 40.0,
        "five_day_accdist": "Big Acc",
    }
    base.update(overrides)
    return GateContext(ticker="BBCA", snapshot_date=_TODAY, **base)


# ── policy value object ──────────────────────────────────────────────────────


def test_default_policy_is_surface():
    assert UnevaluableGatePolicy().action is UnevaluableGateAction.SURFACE
    assert UnevaluableGatePolicy().blocks is False


def test_from_config_accepts_the_two_supported_values():
    assert resolve_policy("surface").blocks is False
    assert resolve_policy("block").blocks is True


def resolve_policy(value: str) -> UnevaluableGatePolicy:
    return UnevaluableGatePolicy.from_config(value)


@pytest.mark.parametrize("value", ["warn", "skip", "", None, True, "BLOCK"])
def test_from_config_fails_closed_on_anything_else(value):
    with pytest.raises(ValueError, match="unevaluable_policy"):
        UnevaluableGatePolicy.from_config(value)


def test_from_config_rejects_a_non_integer_block_confidence():
    with pytest.raises(ValueError, match="unevaluable_block_confidence"):
        UnevaluableGatePolicy.from_config("block", block_confidence="high")


# ── config resolution ────────────────────────────────────────────────────────


def test_absent_config_resolves_to_surface():
    assert resolve_unevaluable_gate_policy({}).action is UnevaluableGateAction.SURFACE


def test_resolver_reads_the_key_and_confidence():
    policy = resolve_unevaluable_gate_policy(
        {
            "risk_engine": {
                "gates": {
                    "unevaluable_policy": "block",
                    "unevaluable_block_confidence": 40,
                }
            }
        }
    )
    assert policy.action is UnevaluableGateAction.BLOCK
    assert policy.block_confidence == 40


def test_resolver_fails_closed_on_an_unknown_configured_value():
    with pytest.raises(ValueError, match="unevaluable_policy"):
        resolve_unevaluable_gate_policy(
            {"risk_engine": {"gates": {"unevaluable_policy": "ignore"}}}
        )


def test_shipped_config_ships_the_non_blocking_default():
    """The file default and the in-code default must agree."""
    shipped = load_engine_config(Path("config/risk_engine.yaml"))
    assert resolve_unevaluable_gate_policy(shipped).action is UnevaluableGateAction.SURFACE


# ── surface: today's behaviour, unchanged ────────────────────────────────────


def test_surface_records_the_unknown_without_blocking():
    resp = _use_case(_SURFACE).execute(
        AssessRiskRequest(ticker="BBCA", gate_context=_ctx(piotroski_f_score=None))
    )
    assert resp.assessment.unevaluable_gates == ("FundamentalGate",)
    assert resp.gate_triggered is None
    assert resp.risk_level == "open"


def test_no_policy_argument_behaves_exactly_like_surface():
    """Omitting the dependency must not silently harden the gate."""
    request = AssessRiskRequest(ticker="BBCA", gate_context=_ctx(piotroski_f_score=None))
    explicit = _use_case(_SURFACE).execute(request)
    omitted = _use_case(None).execute(request)
    assert omitted.gate_triggered == explicit.gate_triggered is None
    assert omitted.assessment.unevaluable_gates == explicit.assessment.unevaluable_gates


# ── block: the explicit opt-in ───────────────────────────────────────────────


def test_block_turns_the_unknown_into_a_verdict():
    resp = _use_case(_BLOCK).execute(
        AssessRiskRequest(ticker="BBCA", gate_context=_ctx(piotroski_f_score=None))
    )
    assert resp.gate_triggered == "FundamentalGate"
    assert resp.risk_level == "BLOCKED"
    assert resp.assessment.gate_is_structural is True
    assert resp.assessment.gate_confidence == 50
    assert "unevaluable_policy=block" in resp.assessment.rationale[0]
    # Still recorded as unevaluable — blocking does not turn it into a trigger.
    assert resp.assessment.unevaluable_gates == ("FundamentalGate",)
    assert {r.gate: r.outcome for r in resp.gate_evaluations}["FundamentalGate"] == "skipped"


def test_block_attributes_the_verdict_to_the_first_unevaluable_gate_and_its_tier():
    resp = _use_case(
        _BLOCK,
        structural=[FundamentalGate(), FreeFloatGate()],
        execution=[BandarGate()],
    ).execute(
        AssessRiskRequest(
            ticker="BBCA",
            gate_context=_ctx(free_float_pct=None, five_day_accdist=None),
        )
    )
    assert resp.gate_triggered == "FreeFloatGate"
    assert resp.assessment.gate_is_structural is True
    assert resp.assessment.unevaluable_gates == ("FreeFloatGate", "BandarGate")


def test_block_does_not_override_a_gate_that_actually_fired():
    resp = _use_case(
        _BLOCK,
        structural=[FundamentalGate(), FreeFloatGate()],
    ).execute(
        AssessRiskRequest(
            ticker="BBCA",
            gate_context=_ctx(piotroski_f_score=1, free_float_pct=None),
        )
    )
    # The real distress verdict wins; the unknown does not relabel it.
    assert resp.gate_triggered == "FundamentalGate"
    assert "F-score" in resp.assessment.rationale[0]


def test_block_is_inert_when_every_gate_reached_a_verdict():
    resp = _use_case(_BLOCK, structural=[FundamentalGate(), FreeFloatGate()]).execute(
        AssessRiskRequest(ticker="BBCA", gate_context=_ctx())
    )
    assert resp.gate_triggered is None
    assert resp.assessment.unevaluable_gates == ()


def test_the_two_policies_disagree_on_the_same_input():
    """Proves the policy is live, so 'unchanged under surface' is not vacuous."""
    request = AssessRiskRequest(ticker="BBCA", gate_context=_ctx(piotroski_f_score=None))
    assert _use_case(_SURFACE).execute(request).gate_triggered is None
    assert _use_case(_BLOCK).execute(request).gate_triggered == "FundamentalGate"


# ── production wiring ────────────────────────────────────────────────────────


def test_accum_composition_root_resolves_the_policy_from_the_shipped_risk_yaml():
    from src.adapters.composition.accumulation_risk_workflow_factory import (
        create_accumulation_assess_risk_use_case,
    )

    use_case = create_accumulation_assess_risk_use_case(
        market_repository=_Repo(_candles()),
        risk_config_path=Path("config/risk_engine.yaml"),
    )
    assert use_case.unevaluable_gate_policy.action is UnevaluableGateAction.SURFACE


def test_accum_composition_root_carries_an_injected_policy_by_identity():
    """Gates injected by identity must not silently fall back to the default."""
    from src.adapters.composition.accumulation_risk_workflow_factory import (
        create_accumulation_assess_risk_use_case,
    )

    use_case = create_accumulation_assess_risk_use_case(
        market_repository=_Repo(_candles()),
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
        unevaluable_gate_policy=_BLOCK,
    )
    assert use_case.unevaluable_gate_policy is _BLOCK


def test_production_policy_bundle_defaults_to_surface():
    from src.application.services.accumulation_production_policy_bundle import (
        AccumulationProductionPolicyBundle,
    )

    field = AccumulationProductionPolicyBundle.__dataclass_fields__["unevaluable_gate_policy"]
    assert field.default == UnevaluableGatePolicy()
