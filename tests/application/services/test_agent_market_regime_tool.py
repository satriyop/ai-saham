"""Offline agent tests for get_market_regime (cohort-scoped, cache-only)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolSideEffect,
)
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_market_regime_tool import (
    MarketRegimeArguments,
    MarketRegimeResultData,
    MarketRegimeTool,
)
from src.domain.value_objects.market_context import (
    ContextFactor,
    MarketContext,
    MarketRegime,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent

_COHORT = "sha256:test-canonical-cohort"
_OTHER_COHORT = "sha256:other-cohort"


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _factor(
    name: str,
    *,
    value: float | None = 1.0,
    label: str = "FAVORABLE",
    enabled: bool = True,
    score: float | None = 0.8,
) -> ContextFactor:
    return ContextFactor(
        name=name,
        enabled=enabled,
        value=value,
        score=score,
        weight=1.0,
        label=label,
        rationale=f"{name} sample",
    )


def _snapshot(
    *,
    as_of: date = date(2026, 8, 1),
    regime: MarketRegime = MarketRegime.RISK_ON,
    conviction: float = 0.72,
    regime_confidence: float | None = 0.55,
    factors: tuple[ContextFactor, ...] | None = None,
    staleness_warning: str | None = None,
    coverage_warning: str | None = None,
    regime_stability: str | None = "STABLE",
    days_in_regime: int | None = 5,
    transition_warning: str | None = None,
) -> MarketContext:
    if factors is None:
        factors = (
            _factor("idx_trend"),
            _factor("idx_breadth", value=0.62),
            _factor("foreign_flow", value=0.1),
            _factor("vix", value=18.0),
            _factor("eido", value=0.02),
            _factor("usd_idr", value=0.0),
        )
    return MarketContext(
        regime=regime,
        conviction=conviction,
        factors=factors,
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=as_of,
        staleness_warning=staleness_warning,
        coverage_warning=coverage_warning,
        regime_confidence=regime_confidence,
        regime_stability=regime_stability,
        days_in_regime=days_in_regime,
        transition_warning=transition_warning,
    )


class _FakeRepo:
    def __init__(self, by_cohort: dict[str, dict[date, MarketContext]] | None = None) -> None:
        self.by_cohort = by_cohort or {}
        self.get_calls: list[tuple[date, str | None]] = []
        self.recent_calls: list[tuple[int, str | None]] = []

    def get(
        self,
        as_of_date: date,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> MarketContext | None:
        self.get_calls.append((as_of_date, semantic_compatibility_id))
        if semantic_compatibility_id is None:
            # Mirror production: multi-cohort without scope is ambiguous → None
            rows = [
                snap
                for cohort_map in self.by_cohort.values()
                for d, snap in cohort_map.items()
                if d == as_of_date
            ]
            return rows[0] if len(rows) == 1 else None
        cohort_map = self.by_cohort.get(semantic_compatibility_id, {})
        return cohort_map.get(as_of_date)

    def get_recent(
        self,
        limit: int = 30,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> list[MarketContext]:
        self.recent_calls.append((limit, semantic_compatibility_id))
        if semantic_compatibility_id is None:
            items: list[MarketContext] = []
            for cohort_map in self.by_cohort.values():
                items.extend(cohort_map.values())
        else:
            items = list(self.by_cohort.get(semantic_compatibility_id, {}).values())
        items.sort(key=lambda c: c.as_of_date, reverse=True)
        return items[:limit]


def _tool(repo: _FakeRepo, **kwargs: Any) -> MarketRegimeTool:
    return MarketRegimeTool(
        repo,
        cohort_id=_COHORT,
        universe_name="idx80",
        benchmark_ticker="IHSG",
        today=lambda: date(2026, 8, 4),
        **kwargs,
    )


def test_definition_facts_not_directive() -> None:
    tool = _tool(_FakeRepo())
    assert tool.definition.name is AgentToolName.GET_MARKET_REGIME
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    desc = tool.definition.description.lower()
    assert "facts only" in desc
    assert "directive" in desc or "not a buy" in desc


def test_happy_path_latest_cohort_scoped() -> None:
    snap = _snapshot()
    repo = _FakeRepo({_COHORT: {snap.as_of_date: snap}, _OTHER_COHORT: {}})
    tool = _tool(repo)
    result = tool.execute("m1", MarketRegimeArguments(as_of=None), _context())
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, MarketRegimeResultData)
    assert result.data.regime == "RISK_ON"
    assert result.data.conviction == 0.72
    assert result.data.regime_confidence == 0.55
    assert result.data.cohort_id == _COHORT
    assert result.data.signal_multiplier == 1.0
    assert result.data.gate_tightening is False
    assert result.data.regime_stability == "STABLE"
    assert result.data.days_in_regime == 5
    assert len(result.data.factors) == 6
    assert not hasattr(result.data.factors[0], "score")
    assert repo.recent_calls == [(1, _COHORT)]
    assert repo.get_calls == []
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_as_of_selects_cohort_not_false_unavailable() -> None:
    """Multi-cohort date must resolve canonical cohort (not false UNAVAILABLE)."""
    as_of = date(2026, 8, 1)
    canonical = _snapshot(as_of=as_of, conviction=0.8)
    other = _snapshot(as_of=as_of, conviction=0.2, regime=MarketRegime.RISK_OFF)
    repo = _FakeRepo(
        {
            _COHORT: {as_of: canonical},
            _OTHER_COHORT: {as_of: other},
        }
    )
    tool = _tool(repo)
    # Unscoped get would be ambiguous (None) — tool must pass cohort
    assert repo.get(as_of) is None
    repo.get_calls.clear()
    result = tool.execute("m2", MarketRegimeArguments(as_of=as_of), _context())
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, MarketRegimeResultData)
    assert result.data.conviction == 0.8
    assert result.data.regime == "RISK_ON"
    assert repo.get_calls == [(as_of, _COHORT)]


def test_regime_confidence_null_is_success_not_partial() -> None:
    snap = _snapshot(regime_confidence=None)
    repo = _FakeRepo({_COHORT: {snap.as_of_date: snap}})
    tool = _tool(repo)
    result = tool.execute("m3", MarketRegimeArguments(as_of=None), _context())
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, MarketRegimeResultData)
    assert result.data.regime_confidence is None


def test_partial_when_factor_missing() -> None:
    snap = _snapshot(
        factors=(
            _factor("idx_trend"),
            _factor("vix", value=None, label="UNAVAILABLE", score=None),
        ),
    )
    repo = _FakeRepo({_COHORT: {snap.as_of_date: snap}})
    tool = _tool(repo)
    result = tool.execute("m4", MarketRegimeArguments(as_of=None), _context())
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "FACTOR_DATA_UNAVAILABLE" in result.warnings
    assert isinstance(result.data, MarketRegimeResultData)


def test_unavailable_when_no_snapshot() -> None:
    tool = _tool(_FakeRepo({}))
    result = tool.execute("m5", MarketRegimeArguments(as_of=None), _context())
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
    assert result.error_code == "MARKET_REGIME_UNAVAILABLE"


def test_future_as_of_unavailable() -> None:
    tool = _tool(_FakeRepo({}))
    result = tool.execute(
        "m6",
        MarketRegimeArguments(as_of=date(2026, 12, 1)),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.error_code == "AS_OF_IN_FUTURE"


def test_no_directive_fields() -> None:
    snap = _snapshot()
    repo = _FakeRepo({_COHORT: {snap.as_of_date: snap}})
    tool = _tool(repo)
    result = tool.execute("m7", MarketRegimeArguments(as_of=None), _context())
    assert isinstance(result.data, MarketRegimeResultData)
    forbidden = {"action", "enter", "size", "directive", "verdict", "buy", "sell"}
    fields = set(result.data.__dataclass_fields__)
    assert fields.isdisjoint(forbidden)
    for f in result.data.factors:
        assert not hasattr(f, "score")


def test_build_arguments_empty_and_iso() -> None:
    tool = _tool(_FakeRepo())
    assert tool.build_arguments(("",)).as_of is None
    assert tool.build_arguments(("2026-08-01",)).as_of == date(2026, 8, 1)
    with pytest.raises(ValueError, match="ISO"):
        tool.build_arguments(("not-a-date",))


def test_cohort_id_required() -> None:
    with pytest.raises(ValueError, match="cohort_id"):
        MarketRegimeTool(_FakeRepo(), cohort_id="")  # type: ignore[arg-type]
