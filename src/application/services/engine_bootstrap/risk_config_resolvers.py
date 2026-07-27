"""
Risk engine config resolving.

Pure config normalization for the Risk Engine: reads risk_engine.yaml,
applies defaults, and builds gate/indicator config value objects. No engine
construction, no infrastructure wiring.
"""

from __future__ import annotations


def _resolve_risk_gates(cfg: dict) -> tuple[list, list]:
    """
    Parse enabled risk gates and return (structural_gates, execution_gates).

    When config is absent/empty, defaults match the previous hardcoded values.
    """
    from src.domain.rules.bandar_gate import BandarGate, BandarGateConfig
    from src.domain.rules.free_float_gate import FreeFloatGate, FreeFloatGatePolicy
    from src.domain.rules.fundamental_gate import FundamentalGate, FundamentalGatePolicy
    from src.domain.rules.liquidity_gate import LiquidityGate, LiquidityGatePolicy

    gates = cfg.get("risk_engine", {}).get("gates", {})

    structural = []
    fund = gates.get("fundamental", {})
    if fund.get("enabled", True):
        structural.append(
            FundamentalGate(
                distress_threshold=fund.get("piotroski_min", 3),
                policy=FundamentalGatePolicy(
                    missing_data_action=fund.get("missing_data_action", "skip"),
                    missing_data_confidence=fund.get("missing_data_confidence", 0),
                    triggered_confidence=fund.get("triggered_confidence", 100),
                    pass_confidence=fund.get("pass_confidence", 100),
                ),
            )
        )

    liq = gates.get("liquidity", {})
    if liq.get("enabled", True):
        structural.append(
            LiquidityGate(
                third_liner_cap_idr=liq.get("market_cap_floor_idr", 1_000_000_000_000),
                liquidity_floor_idr=liq.get("median_tx_floor_idr", 5_000_000_000),
                lookback_days=liq.get("lookback_days", 20),
                policy=LiquidityGatePolicy(
                    missing_data_action=liq.get("missing_data_action", "skip"),
                    missing_data_confidence=liq.get("missing_data_confidence", 0),
                    triggered_confidence=liq.get("triggered_confidence", 100),
                    pass_confidence=liq.get("pass_confidence", 100),
                ),
            )
        )

    ff = gates.get("free_float", {})
    if ff.get("enabled", True):
        structural.append(
            FreeFloatGate(
                min_free_float_pct=ff.get("min_free_float_pct", 15.0),
                policy=FreeFloatGatePolicy(
                    missing_data_action=ff.get("missing_data_action", "skip"),
                    missing_data_confidence=ff.get("missing_data_confidence", 0),
                    triggered_confidence=ff.get("triggered_confidence", 100),
                    pass_confidence=ff.get("pass_confidence", 100),
                ),
            )
        )

    execution = []
    bandar = gates.get("bandar", {})
    if bandar.get("enabled", True):
        execution.append(
            BandarGate(
                BandarGateConfig(
                    distribution_labels=frozenset(
                        bandar.get(
                            "distribution_labels",
                            [
                                "Small Dist",
                                "Big Dist",
                            ],
                        )
                    ),
                    missing_data_action=bandar.get("missing_data_action", "skip"),
                    missing_data_confidence=bandar.get("missing_data_confidence", 0),
                    triggered_confidence=bandar.get("triggered_confidence", 80),
                    pass_confidence=bandar.get("pass_confidence", 100),
                )
            )
        )

    return structural, execution


def resolve_risk_gates(cfg: dict) -> tuple[list, list]:
    """Public wrapper for `_resolve_risk_gates`, for use outside this package."""
    return _resolve_risk_gates(cfg)


def _resolve_risk_indicator_defaults(cfg: dict):
    from src.application.services.risk_engine import RiskIndicatorDefaults

    indicators = cfg.get("risk_engine", {}).get("indicators", {})
    return RiskIndicatorDefaults(
        sma_period=indicators.get("sma_period", 20),
        ema_period=indicators.get("ema_period", 20),
        rsi_period=indicators.get("rsi_period", 14),
        history_days=indicators.get("history_days", 365),
        gate_recent_candle_lookback=indicators.get("gate_recent_candle_lookback", 20),
    )


def _resolve_market_context_gate(cfg: dict):
    from src.application.services.risk_engine import MarketContextGateConfig

    gate = cfg.get("risk_engine", {}).get("market_context_gate", {})
    return MarketContextGateConfig(
        enabled=gate.get("enabled", True),
        block_when_gate_tightening=gate.get("block_when_gate_tightening", True),
        gate_is_structural=gate.get("gate_is_structural", True),
        label_prefix=gate.get("label_prefix", "regime"),
    )


def _resolve_indicator_evaluator_config(cfg: dict):
    from src.application.services.indicator_evaluator import IndicatorEvaluatorConfig

    technical = cfg.get("risk_engine", {}).get("gates", {}).get("technical", {})
    evaluator = technical.get("evaluator", {})
    return IndicatorEvaluatorConfig(
        rsi_overbought=evaluator.get("rsi_overbought", 70.0),
        rsi_oversold=evaluator.get("rsi_oversold", 30.0),
        agreement_count=evaluator.get("agreement_count", 2),
        full_agreement_confidence=evaluator.get("full_agreement_confidence", 100),
        partial_agreement_confidence=evaluator.get("partial_agreement_confidence", 50),
    )


def _resolve_technical_gate_config(cfg: dict):
    from src.domain.rules.technical_gate import TechnicalGateConfig

    technical = cfg.get("risk_engine", {}).get("gates", {}).get("technical", {})
    return TechnicalGateConfig(
        block_when_bearish=technical.get("block_when_bearish", True),
        missing_data_action=technical.get("missing_data_action", "skip"),
        missing_data_confidence=technical.get("missing_data_confidence", 0),
        pass_confidence=technical.get("pass_confidence", 100),
    )
