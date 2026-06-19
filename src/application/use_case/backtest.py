"""
Backtest use case - run strategy backtest on historical data.

Orchestrates rule loading, indicator computation, rule evaluation,
and backtest engine execution to produce deterministic results.

Layer: Application
Depends on: Domain services, Infrastructure loaders, MarketDataRepository
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Union

from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import (
    BUILTIN_INDICATORS,
    IndicatorType,
    SignalMapping,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.services.backtest_engine import BacktestEngine
from src.domain.value_objects.backtest_result import BacktestResult
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.trade_action import TradeAction
from src.infrastructure.config.yaml_loader import YamlConfigLoader


@dataclass
class BacktestRequest:
    """Request DTO for backtest execution."""

    ticker: str
    rules_file: Path | str
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: Decimal = Decimal("100000000")  # 100 million IDR default


@dataclass
class BacktestResponse:
    """Response DTO containing backtest results."""

    ticker: str
    result: BacktestResult

    @property
    def total_return_pct(self) -> Decimal:
        """Convenience property for total return percentage."""
        return self.result.total_return_pct

    @property
    def trade_count(self) -> int:
        """Convenience property for trade count."""
        return self.result.trade_count

    @property
    def win_rate(self) -> Decimal:
        """Convenience property for win rate."""
        return self.result.win_rate

    @property
    def profit_factor(self) -> Decimal:
        """Convenience property for profit factor."""
        return self.result.profit_factor

    @property
    def max_drawdown_pct(self) -> Decimal:
        """Convenience property for max drawdown percentage."""
        return self.result.max_drawdown_pct


class BacktestUseCase:
    """
    Use case for running strategy backtests on historical data.

    This use case:
        1. Loads rules from YAML file
        2. Parses signal_mapping (or uses defaults)
        3. Fetches candles from repository
        4. Computes all required indicators
        5. Builds snapshots and evaluates rules per candle
        6. Maps RiskLevel to TradeAction via SignalMapping
        7. Runs BacktestEngine with computed actions
        8. Returns BacktestResult

    The execution is deterministic: same input -> same output.
    Works fully offline using cached market data.
    """

    def __init__(
        self,
        repository: MarketDataRepository,
        registry: IndicatorRegistry | None = None,
    ) -> None:
        """
        Initialize with repository and optional registry.

        Args:
            repository: MarketDataRepository for fetching cached candles
            registry: IndicatorRegistry for computing indicators.
                     If None, creates default registry (built-ins only).
        """
        self._repository = repository
        self._registry = registry if registry is not None else IndicatorRegistry()

    def execute(self, request: BacktestRequest) -> BacktestResponse:
        """
        Execute backtest for a strategy.

        Args:
            request: Contains ticker, rules file, date range, capital

        Returns:
            BacktestResponse with results and metrics

        Raises:
            ValueError: If ticker invalid or insufficient data
            RulesFileError: If rules file not found
            RulesSchemaError: If rules file has invalid syntax
            RulesValidationError: If rules file has invalid content
        """
        ticker = request.ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")

        # 1. Load rules and get signal mapping (pass registry for indicator validation)
        rule_set = YamlConfigLoader.load(request.rules_file, registry=self._registry)
        interpreter = YamlRuleInterpreter(rule_set)
        signal_mapping = rule_set.signal_mapping or SignalMapping()

        # 2. Fetch candles
        candles = self._fetch_candles(
            ticker=ticker,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        if not candles:
            raise ValueError(
                f"No data available for {ticker}. "
                f"Run 'saham fetch market {ticker} --days 365' first."
            )

        # 3. Get required indicators
        # Pass registry so it can resolve custom formulas (from config/formulas.yaml)
        required_indicators = interpreter.get_required_indicators(registry=self._registry)

        # 4. Compute all indicator series
        indicator_series = self._compute_all_indicators(candles, required_indicators)

        # 5. Build snapshots and evaluate rules for each candle
        actions = self._evaluate_candles(
            candles=candles,
            indicator_series=indicator_series,
            required_indicators=required_indicators,
            interpreter=interpreter,
            signal_mapping=signal_mapping,
        )

        # 6. Run backtest engine
        engine = BacktestEngine(request.initial_capital)
        result = engine.run(
            candles=candles,
            actions=actions,
            strategy_name=rule_set.name,
        )

        return BacktestResponse(ticker=ticker, result=result)

    def _fetch_candles(
        self,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Candle]:
        """
        Fetch candles from repository with optional date filtering.

        Args:
            ticker: Stock ticker
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of candles sorted by date ascending
        """
        # Fetch all available candles first
        candles = self._repository.get_candles(ticker)

        if not candles:
            return []

        # Apply date filters
        if start_date:
            candles = [c for c in candles if c.date >= start_date]
        if end_date:
            candles = [c for c in candles if c.date <= end_date]

        return sorted(candles, key=lambda c: c.date)

    def _compute_all_indicators(
        self,
        candles: list[Candle],
        required_indicators: dict[str, tuple[Union[IndicatorType, str], int]],
    ) -> dict[str, dict[date, Decimal]]:
        """
        Compute all required indicators and return as date-indexed series.

        Uses IndicatorRegistry for unified computation of both built-in
        and plugin indicators.

        Args:
            candles: Historical price data
            required_indicators: Dict mapping name to (type, period).
                                Type can be IndicatorType or string for plugins.

        Returns:
            Dict mapping indicator name to {date: value} dict
        """
        result: dict[str, dict[date, Decimal]] = {}

        for name, (ind_type, period) in required_indicators.items():
            # Get type name as string for registry lookup
            type_name = (
                ind_type.value if isinstance(ind_type, IndicatorType) else ind_type
            )
            values = self._registry.compute(type_name, candles, period)
            # Convert list of tuples to date-indexed dict
            result[name] = {d: v for d, v in values}

        return result

    def _evaluate_candles(
        self,
        candles: list[Candle],
        indicator_series: dict[str, dict[date, Decimal]],
        required_indicators: dict[str, tuple[Union[IndicatorType, str], int]],
        interpreter: YamlRuleInterpreter,
        signal_mapping: SignalMapping,
    ) -> list[tuple[date, TradeAction, str]]:
        """
        Evaluate rules for each candle and return trade actions.

        Only evaluates candles where all required indicators are available.

        Args:
            candles: Historical price data
            indicator_series: Pre-computed indicator values by date
            required_indicators: Required indicator definitions
            interpreter: Rule interpreter for evaluation
            signal_mapping: Maps risk levels to trade actions

        Returns:
            List of (date, action, rule_name) tuples
        """
        actions: list[tuple[date, TradeAction, str]] = []

        for candle in candles:
            # Check if all indicators are available for this date
            snapshot = self._build_snapshot_for_date(
                candle.date,
                indicator_series,
                required_indicators,
                candle=candle,
            )

            if snapshot is None:
                # Not enough data yet (warm-up period)
                actions.append((candle.date, TradeAction.FLAT, "warm_up"))
                continue

            # Evaluate rules
            risk_level, confidence, rationale = interpreter.evaluate(snapshot)

            # Map to trade action
            action = signal_mapping.get_action(risk_level)

            # Extract rule name from rationale
            rule_name = self._extract_rule_name(rationale)

            actions.append((candle.date, action, rule_name))

        return actions

    def _build_snapshot_for_date(
        self,
        target_date: date,
        indicator_series: dict[str, dict[date, Decimal]],
        required_indicators: dict[str, tuple[Union[IndicatorType, str], int]],
        candle: Candle | None = None,
    ) -> IndicatorSnapshot | None:
        """
        Build an IndicatorSnapshot for a specific date.

        Returns None if any required indicator is not available for this date.

        Args:
            target_date: Date to build snapshot for
            indicator_series: Pre-computed indicator values
            required_indicators: Required indicator definitions
            candle: Optional candle to inject price fields (OPEN, HIGH, LOW, CLOSE, VOLUME)

        Returns:
            IndicatorSnapshot if all indicators available, None otherwise
        """
        values: dict[str, Decimal] = {}

        # Collect all indicator values for this date
        for name in required_indicators:
            if name not in indicator_series:
                return None
            if target_date not in indicator_series[name]:
                return None
            values[name] = indicator_series[name][target_date]

        # Extract built-in indicator values (or defaults)
        sma_value = values.get("SMA", Decimal("0"))
        ema_value = values.get("EMA", Decimal("0"))
        rsi_value = values.get("RSI", Decimal("0"))

        # Build extras for custom indicators
        extras: list[tuple[str, Decimal]] = []
        for name, value in values.items():
            if name not in BUILTIN_INDICATORS:
                extras.append((name, value))

        # Inject price fields from candle data (OPEN, HIGH, LOW, CLOSE, VOLUME)
        if candle is not None:
            extras.append(("OPEN", candle.open))
            extras.append(("HIGH", candle.high))
            extras.append(("LOW", candle.low))
            extras.append(("CLOSE", candle.close))
            extras.append(("VOLUME", Decimal(candle.volume)))

        return IndicatorSnapshot(
            date=target_date,
            sma=sma_value,
            ema=ema_value,
            rsi=rsi_value,
            extras=tuple(extras),
        )

    def _extract_rule_name(self, rationale: list[str]) -> str:
        """
        Extract rule name from rationale list.

        Args:
            rationale: List of rationale strings from rule evaluation

        Returns:
            Rule name or "default" if no rule matched
        """
        if not rationale:
            return "default"

        # First item typically contains rule name
        first = rationale[0]
        if "rule '" in first.lower():
            # Extract name from "Custom rule 'rule_name' matched"
            start = first.find("'") + 1
            end = first.find("'", start)
            if start > 0 and end > start:
                return first[start:end]

        if "default" in first.lower():
            return "default"

        return "unknown"
