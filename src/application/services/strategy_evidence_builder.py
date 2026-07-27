"""Build diagnostic strategy evidence from validated strategy YAMLs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Union

from src.application.ports.rules_loader import RulesLoader
from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import BUILTIN_INDICATORS, IndicatorType
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.strategy_loader import StrategyLoader
from src.domain.entities.candle import Candle
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
from src.domain.value_objects.strategy_evidence import (
    StrategyEvidence,
    StrategyEvidenceOutcome,
    StrategyRuleEvidence,
)


@dataclass(frozen=True)
class StrategyEvidenceRequest:
    ticker: str
    strategy_name: str | Path
    candles: tuple[Candle, ...] | list[Candle]
    snapshot_date: date
    setup_family: str | None = None
    setup_phase: SetupPhaseSnapshot | str | None = None


class StrategyEvidenceBuilder:
    """Evaluate a strategy YAML against the current candle snapshot.

    The output is diagnostic-only. It is intended for replay attribution and
    human inspection, not for changing setup phase or entry decisions.
    """

    def __init__(
        self,
        registry: IndicatorRegistry | None = None,
        loader: StrategyLoader | None = None,
        rules_loader: RulesLoader | None = None,
    ) -> None:
        self._registry = registry if registry is not None else IndicatorRegistry()
        if loader is not None:
            self._loader = loader
        else:
            if rules_loader is None:
                raise ValueError("rules_loader is required when loader is not provided")
            self._loader = StrategyLoader(rules_loader=rules_loader, registry=self._registry)

    def build(self, request: StrategyEvidenceRequest) -> StrategyEvidence:
        ticker = request.ticker.upper().strip()
        strategy_ref = str(request.strategy_name)
        candles = sorted(tuple(request.candles), key=lambda c: c.date)
        if not candles:
            return self._unavailable(
                ticker=ticker,
                snapshot_date=request.snapshot_date,
                strategy_name=strategy_ref,
                reasons=("no_candles",),
            )

        try:
            rule_set = self._loader.load(strategy_ref)
            interpreter = YamlRuleInterpreter(rule_set)
            required_indicators = interpreter.get_required_indicators(registry=self._registry)
            indicator_series = self._compute_all_indicators(
                candles,
                required_indicators,
            )
            latest = candles[-1]
            snapshot = self._build_snapshot_for_date(
                latest.date,
                indicator_series,
                required_indicators,
                latest,
            )
            coverage = self._coverage_score(
                latest.date,
                indicator_series,
                required_indicators,
            )
            freshness = self._freshness_score(latest.date, request.snapshot_date)
            if snapshot is None:
                return StrategyEvidence(
                    ticker=ticker,
                    snapshot_date=request.snapshot_date,
                    strategy_name=rule_set.name,
                    outcome=StrategyEvidenceOutcome.UNAVAILABLE,
                    coverage_score=coverage,
                    conviction_score=0.0,
                    freshness_score=freshness,
                    unavailable_reasons=("indicator_warmup_or_missing",),
                    metadata={
                        "required_indicators": sorted(required_indicators.keys()),
                        "latest_candle_date": latest.date.isoformat(),
                    },
                )

            risk_level, confidence, rationale = interpreter.evaluate(snapshot)
            matched_rule_name = self._extract_rule_name(rationale)
            outcome = (
                StrategyEvidenceOutcome.MATCHED
                if confidence > 0 and matched_rule_name is not None
                else StrategyEvidenceOutcome.NOT_MATCHED
            )
            rule_evidence = StrategyRuleEvidence(
                strategy_name=rule_set.name,
                rule_name=matched_rule_name,
                rule_outcome=risk_level.value,
                evidence_route=self._route_for(risk_level),
                setup_family=request.setup_family,
                setup_phase=self._phase_name(request.setup_phase),
                rationale=tuple(rationale),
            )
            return StrategyEvidence(
                ticker=ticker,
                snapshot_date=request.snapshot_date,
                strategy_name=rule_set.name,
                outcome=outcome,
                matched_rule=rule_evidence,
                coverage_score=coverage,
                conviction_score=round(float(confidence) / 100.0, 4),
                freshness_score=freshness,
                rationale=tuple(rationale),
                metadata={
                    "required_indicators": sorted(required_indicators.keys()),
                    "latest_candle_date": latest.date.isoformat(),
                    "diagnostic_only": True,
                },
            )
        except Exception as exc:
            return self._unavailable(
                ticker=ticker,
                snapshot_date=request.snapshot_date,
                strategy_name=strategy_ref,
                reasons=(f"strategy_evaluation_failed:{exc}",),
                outcome=StrategyEvidenceOutcome.INVALID,
            )

    def _compute_all_indicators(
        self,
        candles: tuple[Candle, ...],
        required_indicators: dict[str, tuple[Union[IndicatorType, str], int]],
    ) -> dict[str, dict[date, Decimal]]:
        result: dict[str, dict[date, Decimal]] = {}
        for name, (ind_type, period) in required_indicators.items():
            type_name = ind_type.value if isinstance(ind_type, IndicatorType) else str(ind_type)
            values = self._registry.compute(type_name, list(candles), period)
            result[name] = {d: v for d, v in values}
        return result

    def _build_snapshot_for_date(
        self,
        target_date: date,
        indicator_series: dict[str, dict[date, Decimal]],
        required_indicators: dict[str, tuple[Union[IndicatorType, str], int]],
        candle: Candle,
    ) -> IndicatorSnapshot | None:
        values: dict[str, Decimal] = {}
        for name in required_indicators:
            if target_date not in indicator_series.get(name, {}):
                return None
            values[name] = indicator_series[name][target_date]

        extras = [(name, value) for name, value in values.items() if name not in BUILTIN_INDICATORS]
        extras.extend(
            [
                ("OPEN", candle.open),
                ("HIGH", candle.high),
                ("LOW", candle.low),
                ("CLOSE", candle.close),
                ("VOLUME", Decimal(candle.volume)),
            ]
        )
        return IndicatorSnapshot(
            date=target_date,
            sma=values.get("SMA", Decimal("0")),
            ema=values.get("EMA", Decimal("0")),
            rsi=values.get("RSI", Decimal("0")),
            extras=tuple(extras),
        )

    def _coverage_score(
        self,
        target_date: date,
        indicator_series: dict[str, dict[date, Decimal]],
        required_indicators: dict[str, tuple[Union[IndicatorType, str], int]],
    ) -> float:
        if not required_indicators:
            return 1.0
        available = sum(
            1 for name in required_indicators if target_date in indicator_series.get(name, {})
        )
        return round(available / len(required_indicators), 4)

    @staticmethod
    def _freshness_score(latest_candle_date: date, snapshot_date: date) -> float:
        age = max((snapshot_date - latest_candle_date).days, 0)
        if age == 0:
            return 1.0
        if age <= 3:
            return 0.8
        if age <= 7:
            return 0.5
        return 0.2

    @staticmethod
    def _route_for(risk_level: RiskLevel) -> str:
        if risk_level == RiskLevel.LOW_RISK:
            return "strategy_yaml_supportive"
        if risk_level == RiskLevel.HIGH_RISK:
            return "strategy_yaml_caution"
        return "strategy_yaml_neutral"

    @staticmethod
    def _phase_name(phase: SetupPhaseSnapshot | str | None) -> str | None:
        if phase is None:
            return None
        if isinstance(phase, str):
            return phase
        return phase.current_phase.value

    @staticmethod
    def _extract_rule_name(rationale: list[str]) -> str | None:
        for item in rationale:
            if "rule '" in item.lower():
                start = item.find("'") + 1
                end = item.find("'", start)
                if start > 0 and end > start:
                    return item[start:end]
        return None

    @staticmethod
    def _unavailable(
        *,
        ticker: str,
        snapshot_date: date,
        strategy_name: str,
        reasons: tuple[str, ...],
        outcome: StrategyEvidenceOutcome = StrategyEvidenceOutcome.UNAVAILABLE,
    ) -> StrategyEvidence:
        return StrategyEvidence(
            ticker=ticker,
            snapshot_date=snapshot_date,
            strategy_name=strategy_name,
            outcome=outcome,
            coverage_score=0.0,
            conviction_score=0.0,
            freshness_score=None,
            unavailable_reasons=reasons,
            metadata={"diagnostic_only": True},
        )
