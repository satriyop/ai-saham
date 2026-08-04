"""Offline tests for BuildTickerResearchBriefUseCase (authority + sections)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.application.use_case.build_ticker_research_brief_use_case import (
    SECTION_FOREIGN_FLOW,
    SECTION_JUDGE,
    SECTION_OWNERSHIP,
    SECTION_REGIME,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
    STATUS_UNAVAILABLE,
    BuildTickerResearchBriefRequest,
    BuildTickerResearchBriefUseCase,
    normalize_sections,
    parse_sections_csv,
)
from src.application.use_case.view_ticker_foreign_history_use_case import (
    ViewTickerForeignHistoryResult,
)
from src.domain.entities.broker_flow import ForeignFlowPoint
from src.domain.value_objects.market_context import (
    ContextFactor,
    MarketContext,
    MarketRegime,
)
from src.domain.value_objects.shareholding_composition import ShareholdingComposition

pytestmark = pytest.mark.agent


class _Foreign:
    def __init__(self, result: ViewTickerForeignHistoryResult | None) -> None:
        self.result = result
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return self.result


class _Ownership:
    def __init__(self, composition) -> None:
        self.composition = composition

    def get_ownership(self, ticker: str):
        return self.composition


class _RegimeRepo:
    def __init__(self, snap: MarketContext | None) -> None:
        self.snap = snap
        self.recent_calls: list[tuple[int, str | None]] = []

    def get(self, as_of_date, *, semantic_compatibility_id=None):
        return self.snap if self.snap and self.snap.as_of_date == as_of_date else None

    def get_recent(self, limit=30, *, semantic_compatibility_id=None):
        self.recent_calls.append((limit, semantic_compatibility_id))
        return [self.snap] if self.snap else []


def _foreign_result() -> ViewTickerForeignHistoryResult:
    points = (
        ForeignFlowPoint(
            ticker="BBCA",
            date=date(2026, 7, 30),
            net_val=Decimal("1"),
            net_lot=1,
            avg_price=Decimal("100"),
        ),
        ForeignFlowPoint(
            ticker="BBCA",
            date=date(2026, 7, 31),
            net_val=Decimal("3"),
            net_lot=2,
            avg_price=Decimal("101"),
        ),
    )
    return ViewTickerForeignHistoryResult(
        ticker="BBCA",
        days=2,
        requested_source="auto",
        resolved_source="stockbit",
        points=points,
        as_of=date(2026, 7, 31),
    )


def _ownership() -> ShareholdingComposition:
    return ShareholdingComposition(
        ticker="BBCA",
        report_date=date(2026, 6, 30),
        institution_pct=55.0,
        individual_pct=45.0,
        top_holder_name="FOO",
        top_holder_pct=12.0,
        total_shares=1_000_000,
    )


def _regime_snap() -> MarketContext:
    return MarketContext(
        regime=MarketRegime.RISK_ON,
        conviction=0.7,
        factors=(
            ContextFactor(
                name="idx_trend",
                enabled=True,
                value=1.0,
                score=0.8,
                weight=1.0,
                label="FAVORABLE",
                rationale="up",
            ),
        ),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=date(2026, 8, 1),
        regime_confidence=0.4,
    )


def test_normalize_and_parse_sections() -> None:
    assert normalize_sections(()) == (
        SECTION_JUDGE,
        "broker_flow",
        SECTION_FOREIGN_FLOW,
        SECTION_OWNERSHIP,
        "corporate_actions",
        SECTION_REGIME,
    )
    assert parse_sections_csv("regime,judge") == (SECTION_JUDGE, SECTION_REGIME)
    with pytest.raises(ValueError, match="unknown"):
        parse_sections_csv("verdict")


def test_partial_when_sections_degrade_independently() -> None:
    uc = BuildTickerResearchBriefUseCase(
        foreign_history=_Foreign(_foreign_result()),
        ownership_source=_Ownership(None),
        market_context_repository=_RegimeRepo(_regime_snap()),
        regime_cohort_id="sha256:c",
        judge_ticker=None,
    )
    result = uc.execute(
        BuildTickerResearchBriefRequest(
            ticker="BBCA",
            sections=(SECTION_JUDGE, SECTION_FOREIGN_FLOW, SECTION_OWNERSHIP, SECTION_REGIME),
            foreign_days=2,
        )
    )
    assert result.overall_status == STATUS_PARTIAL
    assert result.foreign_flow is not None
    assert result.regime is not None
    assert result.ownership is None
    assert result.judge is None
    meta_by_name = {m.name: m for m in result.section_meta}
    assert meta_by_name[SECTION_JUDGE].status == STATUS_UNAVAILABLE
    assert meta_by_name[SECTION_FOREIGN_FLOW].status == STATUS_SUCCESS
    assert meta_by_name[SECTION_OWNERSHIP].status == STATUS_UNAVAILABLE
    assert meta_by_name[SECTION_REGIME].status == STATUS_SUCCESS


def test_authority_guard_no_minted_verdict_fields() -> None:
    uc = BuildTickerResearchBriefUseCase(
        foreign_history=_Foreign(_foreign_result()),
        ownership_source=_Ownership(_ownership()),
        market_context_repository=_RegimeRepo(_regime_snap()),
        regime_cohort_id="sha256:c",
    )
    result = uc.execute(
        BuildTickerResearchBriefRequest(
            ticker="BBCA",
            sections=(SECTION_FOREIGN_FLOW, SECTION_OWNERSHIP, SECTION_REGIME),
        )
    )
    forbidden = {
        "verdict",
        "brief_conclusion",
        "recommendation",
        "overall_action",
        "composite_score",
        "enter",
        "size",
    }
    assert set(result.__dataclass_fields__).isdisjoint(forbidden)
    # Engine Action only appears under judge section when present
    assert result.judge is None
    assert not hasattr(result, "action")


def test_regime_cohort_scoped_latest() -> None:
    repo = _RegimeRepo(_regime_snap())
    uc = BuildTickerResearchBriefUseCase(
        market_context_repository=repo,
        regime_cohort_id="sha256:canonical",
    )
    result = uc.execute(BuildTickerResearchBriefRequest(ticker="BBCA", sections=(SECTION_REGIME,)))
    assert result.regime is not None
    assert result.regime.cohort_id == "sha256:canonical"
    assert repo.recent_calls == [(1, "sha256:canonical")]
    assert not hasattr(result.regime.factors[0], "score")


def test_happy_subset_all_success() -> None:
    uc = BuildTickerResearchBriefUseCase(
        foreign_history=_Foreign(_foreign_result()),
        ownership_source=_Ownership(_ownership()),
        market_context_repository=_RegimeRepo(_regime_snap()),
        regime_cohort_id="sha256:c",
    )
    result = uc.execute(
        BuildTickerResearchBriefRequest(
            ticker="bbca",
            sections=(SECTION_FOREIGN_FLOW, SECTION_OWNERSHIP, SECTION_REGIME),
            foreign_days=2,
        )
    )
    assert result.ticker == "BBCA"
    assert result.overall_status == STATUS_SUCCESS
    assert result.foreign_flow is not None
    assert result.ownership is not None
    assert result.regime is not None
