"""
SourceSettlementRegistry — per-source settlement rules for DQ-002F.

Explicit, deterministic registry describing *how* each authoritative Phase 2
source family settles relative to a decision timestamp: whether it is judged
against the IDX session calendar (candles, broker data) or against a raw
fetch/observation timestamp (enrichment caches, market context), and whether
it is even capable of being authoritative at all (sentiment is not, ever).

This is config-as-code, not a YAML file, deliberately: the rule set is a
small, stable, developer-reviewed table, not something an operator tunes at
runtime — the same convention already used by
`StaticSourceFieldContractCatalog` for DQ-001's field contracts.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum


class SettlementBasis(str, Enum):
    """How a source family's availability is judged against `decision_at`."""

    # Judged against the IDX session calendar: compare the source's
    # `observed_through` date to `effective_session.latest_completed_session`.
    SESSION_ALIGNED = "SESSION_ALIGNED"

    # Judged directly against a fetch/observation timestamp: compare
    # `available_at` to `decision_at`, independent of session alignment.
    FETCH_TIMESTAMP = "FETCH_TIMESTAMP"

    # Never authoritative regardless of timing (sentiment).
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"


@dataclass(frozen=True)
class SourceSettlementRule:
    """Deterministic settlement policy for one source family.

    `settlement_lag_days` only applies to `SESSION_ALIGNED` sources: the
    number of sessions a source is *expected* to lag the IDX close before it
    is judged `STALE` rather than merely `LATE`. Candles have zero lag (any
    gap is immediately `STALE`); broker/flow data is allowed a small,
    explicit lag before being penalized.

    `max_staleness_days` only applies to `FETCH_TIMESTAMP` sources: the
    maximum age (in days, relative to `decision_at`) before a fetched
    snapshot is judged `STALE` rather than `CURRENT`. `None` means no cap is
    enforced (age alone never makes it `STALE`).

    `provider_cutoff_time` (DQ-002H) only applies to `SESSION_ALIGNED`
    sources: a policy-owned (not provider-published) WIB wall-clock time by
    which a lagged source's data is expected to have settled for its
    lagged session. It is purely informational/explanatory — it does
    **not** change whether a source is `LATE` vs `STALE`; that remains
    governed exclusively by `settlement_lag_days` (see
    `AssessSourceAvailabilityUseCase._assess_session_aligned`). Combined
    with the lagged session's date and `IDX_TIMEZONE` to produce
    `SourceAvailabilityAssessment.expected_available_at`.
    """

    source_family: str
    settlement_basis: SettlementBasis
    is_authoritative_capable: bool
    settlement_lag_days: int = 0
    max_staleness_days: int | None = None
    provider_cutoff_time: time | None = None

    def __post_init__(self) -> None:
        if self.settlement_basis is SettlementBasis.DIAGNOSTIC_ONLY and (
            self.is_authoritative_capable
        ):
            raise ValueError(
                f"source family '{self.source_family}' is DIAGNOSTIC_ONLY and must not "
                "be is_authoritative_capable=True; sentiment-class sources can never "
                "become authoritative."
            )
        if (
            self.provider_cutoff_time is not None
            and self.settlement_basis is not SettlementBasis.SESSION_ALIGNED
        ):
            raise ValueError(
                f"source family '{self.source_family}' sets provider_cutoff_time but is "
                f"not SESSION_ALIGNED ({self.settlement_basis.value}); provider cutoffs "
                "are only meaningful for session-aligned sources."
            )


class SourceSettlementRegistry:
    """Deterministic lookup of `SourceSettlementRule` by source family."""

    def __init__(self, rules: dict[str, SourceSettlementRule]) -> None:
        self._rules = dict(rules)

    def rule_for(self, source_family: str) -> SourceSettlementRule | None:
        return self._rules.get(source_family)

    def source_families(self) -> tuple[str, ...]:
        return tuple(self._rules.keys())


# DQ-002H: policy-owned placeholder provider settlement cutoff for broker/flow
# sources, expressed in WIB (IDX_TIMEZONE). This is NOT a documented Stockbit/
# IDX provider SLA — no such published cutoff was found in `docs/` or
# `config/` at the time this was added. It is a conservative, explicit
# placeholder (end-of-day, well after the 16:00 WIB market close) so cutoff
# visibility exists and is reviewable, rather than an undocumented implicit
# assumption. Revise this constant (and this comment) if a real provider SLA
# is ever documented.
BROKER_PROVIDER_CUTOFF_WIB = time(20, 0)

_DEFAULT_RULES: dict[str, SourceSettlementRule] = {
    "candles": SourceSettlementRule(
        source_family="candles",
        settlement_basis=SettlementBasis.SESSION_ALIGNED,
        is_authoritative_capable=True,
        settlement_lag_days=0,
        # No provider cutoff: candles have zero allowed lag (any gap is
        # immediately STALE), so a settlement cutoff concept does not apply.
    ),
    "broker_summaries": SourceSettlementRule(
        source_family="broker_summaries",
        settlement_basis=SettlementBasis.SESSION_ALIGNED,
        is_authoritative_capable=True,
        settlement_lag_days=1,
        provider_cutoff_time=BROKER_PROVIDER_CUTOFF_WIB,
    ),
    "broker_daily_flow": SourceSettlementRule(
        source_family="broker_daily_flow",
        settlement_basis=SettlementBasis.SESSION_ALIGNED,
        is_authoritative_capable=True,
        settlement_lag_days=1,
        provider_cutoff_time=BROKER_PROVIDER_CUTOFF_WIB,
    ),
    "foreign_flow_points": SourceSettlementRule(
        source_family="foreign_flow_points",
        settlement_basis=SettlementBasis.SESSION_ALIGNED,
        is_authoritative_capable=True,
        settlement_lag_days=1,
        provider_cutoff_time=BROKER_PROVIDER_CUTOFF_WIB,
    ),
    "foreign_flow_snapshots": SourceSettlementRule(
        source_family="foreign_flow_snapshots",
        settlement_basis=SettlementBasis.SESSION_ALIGNED,
        is_authoritative_capable=True,
        settlement_lag_days=1,
        provider_cutoff_time=BROKER_PROVIDER_CUTOFF_WIB,
    ),
    "analyst_cache": SourceSettlementRule(
        source_family="analyst_cache",
        settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
        is_authoritative_capable=True,
        max_staleness_days=90,
    ),
    "company_fundamentals": SourceSettlementRule(
        source_family="company_fundamentals",
        settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
        is_authoritative_capable=True,
        max_staleness_days=120,
    ),
    "seasonality_cache": SourceSettlementRule(
        source_family="seasonality_cache",
        settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
        is_authoritative_capable=True,
        max_staleness_days=45,
    ),
    "corporate_action_events": SourceSettlementRule(
        source_family="corporate_action_events",
        settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
        is_authoritative_capable=True,
        max_staleness_days=30,
    ),
    "corporate_action_event_dates": SourceSettlementRule(
        source_family="corporate_action_event_dates",
        settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
        is_authoritative_capable=True,
        max_staleness_days=30,
    ),
    "market_context_snapshots": SourceSettlementRule(
        source_family="market_context_snapshots",
        settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
        is_authoritative_capable=True,
        max_staleness_days=1,
    ),
    "regime_observations": SourceSettlementRule(
        source_family="regime_observations",
        settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
        is_authoritative_capable=True,
        max_staleness_days=1,
    ),
    "sentiment": SourceSettlementRule(
        source_family="sentiment",
        settlement_basis=SettlementBasis.DIAGNOSTIC_ONLY,
        is_authoritative_capable=False,
    ),
}


def default_source_settlement_registry() -> SourceSettlementRegistry:
    """Canonical Phase 2 registry. Construct a fresh instance per call so
    callers never share/mutate a process-wide singleton dict."""

    return SourceSettlementRegistry(dict(_DEFAULT_RULES))
