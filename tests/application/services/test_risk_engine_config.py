from src.application.services.bootstrap import _resolve_risk_gates
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate


def test_resolve_risk_gates_reads_liquidity_market_cap_floor():
    structural, execution = _resolve_risk_gates({
        "risk_engine": {
            "gates": {
                "fundamental": {"enabled": True, "piotroski_min": 4},
                "liquidity": {
                    "enabled": True,
                    "market_cap_floor_idr": 500_000_000_000,
                    "median_tx_floor_idr": 3_000_000_000,
                    "lookback_days": 10,
                },
                "free_float": {"enabled": True, "min_free_float_pct": 20.0},
                "bandar": {"enabled": True},
            }
        }
    })

    fundamental = next(g for g in structural if isinstance(g, FundamentalGate))
    liquidity = next(g for g in structural if isinstance(g, LiquidityGate))
    free_float = next(g for g in structural if isinstance(g, FreeFloatGate))

    assert fundamental._threshold == 4
    assert liquidity._cap_threshold == 500_000_000_000
    assert liquidity._liquidity_floor == 3_000_000_000
    assert liquidity._lookback == 10
    assert free_float._threshold == 20.0
    assert any(isinstance(g, BandarGate) for g in execution)


def test_resolve_risk_gates_omits_disabled_gates():
    structural, execution = _resolve_risk_gates({
        "risk_engine": {
            "gates": {
                "fundamental": {"enabled": False},
                "liquidity": {"enabled": False},
                "free_float": {"enabled": False},
                "bandar": {"enabled": False},
            }
        }
    })

    assert structural == []
    assert execution == []
