from src.application.services.bootstrap import (
    _resolve_indicator_evaluator_config,
    _resolve_market_context_gate,
    _resolve_risk_gates,
    _resolve_risk_indicator_defaults,
    _resolve_technical_gate_config,
)
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate


def test_resolve_risk_gates_reads_liquidity_market_cap_floor():
    structural, execution = _resolve_risk_gates({
        "risk_engine": {
            "gates": {
                "fundamental": {
                    "enabled": True,
                    "piotroski_min": 4,
                    "missing_data_action": "block",
                    "missing_data_confidence": 25,
                    "triggered_confidence": 95,
                    "pass_confidence": 85,
                },
                "liquidity": {
                    "enabled": True,
                    "market_cap_floor_idr": 500_000_000_000,
                    "median_tx_floor_idr": 3_000_000_000,
                    "lookback_days": 10,
                    "missing_data_action": "block",
                    "missing_data_confidence": 20,
                    "triggered_confidence": 90,
                    "pass_confidence": 80,
                },
                "free_float": {
                    "enabled": True,
                    "min_free_float_pct": 20.0,
                    "missing_data_action": "block",
                    "missing_data_confidence": 15,
                    "triggered_confidence": 88,
                    "pass_confidence": 78,
                },
                "bandar": {"enabled": True},
                "technical": {"block_when_bearish": False},
            }
        }
    })

    fundamental = next(g for g in structural if isinstance(g, FundamentalGate))
    liquidity = next(g for g in structural if isinstance(g, LiquidityGate))
    free_float = next(g for g in structural if isinstance(g, FreeFloatGate))

    assert fundamental._threshold == 4
    assert fundamental._policy.missing_data_action == "block"
    assert fundamental._policy.missing_data_confidence == 25
    assert fundamental._policy.triggered_confidence == 95
    assert fundamental._policy.pass_confidence == 85
    assert liquidity._cap_threshold == 500_000_000_000
    assert liquidity._liquidity_floor == 3_000_000_000
    assert liquidity._lookback == 10
    assert liquidity._policy.missing_data_action == "block"
    assert liquidity._policy.missing_data_confidence == 20
    assert liquidity._policy.triggered_confidence == 90
    assert liquidity._policy.pass_confidence == 80
    assert free_float._threshold == 20.0
    assert free_float._policy.missing_data_action == "block"
    assert free_float._policy.missing_data_confidence == 15
    assert free_float._policy.triggered_confidence == 88
    assert free_float._policy.pass_confidence == 78
    assert any(isinstance(g, BandarGate) for g in execution)


def test_resolve_risk_gates_reads_bandar_policy():
    _, execution = _resolve_risk_gates({
        "risk_engine": {
            "gates": {
                "fundamental": {"enabled": False},
                "liquidity": {"enabled": False},
                "free_float": {"enabled": False},
                "bandar": {
                    "enabled": True,
                    "distribution_labels": ["Custom Dist"],
                    "missing_data_action": "block",
                    "missing_data_confidence": 30,
                    "triggered_confidence": 70,
                    "pass_confidence": 90,
                },
            }
        }
    })

    bandar = next(g for g in execution if isinstance(g, BandarGate))
    assert bandar._config.distribution_labels == frozenset({"Custom Dist"})
    assert bandar._config.missing_data_action == "block"
    assert bandar._config.missing_data_confidence == 30
    assert bandar._config.triggered_confidence == 70
    assert bandar._config.pass_confidence == 90


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


def test_resolve_risk_runtime_policy_blocks():
    cfg = {
        "risk_engine": {
            "indicators": {
                "sma_period": 50,
                "ema_period": 21,
                "rsi_period": 10,
                "history_days": 500,
                "gate_recent_candle_lookback": 30,
            },
            "market_context_gate": {
                "enabled": False,
                "block_when_gate_tightening": False,
                "gate_is_structural": False,
                "label_prefix": "macro",
            },
            "gates": {
                "technical": {
                    "block_when_bearish": False,
                    "missing_data_action": "block",
                    "missing_data_confidence": 35,
                    "pass_confidence": 75,
                    "evaluator": {
                        "rsi_overbought": 75.0,
                        "rsi_oversold": 25.0,
                        "agreement_count": 3,
                        "full_agreement_confidence": 95,
                        "partial_agreement_confidence": 45,
                    },
                }
            },
        }
    }

    defaults = _resolve_risk_indicator_defaults(cfg)
    market_gate = _resolve_market_context_gate(cfg)
    evaluator = _resolve_indicator_evaluator_config(cfg)
    technical = _resolve_technical_gate_config(cfg)

    assert defaults.sma_period == 50
    assert defaults.ema_period == 21
    assert defaults.rsi_period == 10
    assert defaults.history_days == 500
    assert defaults.gate_recent_candle_lookback == 30
    assert market_gate.enabled is False
    assert market_gate.block_when_gate_tightening is False
    assert market_gate.gate_is_structural is False
    assert market_gate.label_prefix == "macro"
    assert evaluator.rsi_overbought == 75.0
    assert evaluator.rsi_oversold == 25.0
    assert evaluator.agreement_count == 3
    assert evaluator.full_agreement_confidence == 95
    assert evaluator.partial_agreement_confidence == 45
    assert technical.block_when_bearish is False
    assert technical.missing_data_action == "block"
    assert technical.missing_data_confidence == 35
    assert technical.pass_confidence == 75
