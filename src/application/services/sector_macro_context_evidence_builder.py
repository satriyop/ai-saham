"""SectorMacroContextEvidenceBuilder — pure application service (ADR-053).

Computes routed macro-driver diagnostics from preloaded series candles.

Design invariants:
- NEVER fetches data. All candles arrive on the request.
- NEVER raises from build(); errors degrade to unavailable / UNKNOWN.
- evidence_status is always DIAGNOSTIC in v1.
- Return units are fractional (0.05 = +5%), matching L2a sector context
  (NOT MCE pct_return which is percent units).

Layer: Application. Depends only on domain entities/VOs + stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.policy_rate_step import PolicyRateStep
from src.domain.value_objects.sector_macro_context_evidence import (
    MacroFactorScore,
    SectorMacroContextEvidence,
)

_ALLOWED_KINDS = frozenset({"return_sessions", "policy_rate_steps"})
_DEFAULT_POLICY_LOOKBACK_DAYS = 180


@dataclass(frozen=True)
class FactorThresholds:
    supportive_min: float
    headwind_max: float


@dataclass(frozen=True)
class FactorLibraryEntry:
    name: str
    series: str
    kind: str
    invert: bool
    thresholds: FactorThresholds
    lookback_days: int | None = None  # policy_rate_steps calendar-day window


@dataclass(frozen=True)
class SectorMapFactorRef:
    ref: str
    weight: float


@dataclass(frozen=True)
class SectorMacroContextConfig:
    evidence_status: EvidenceStatus
    lookback_sessions: int
    min_valid_sessions: int
    min_coverage_to_label: float
    favorable_min: float
    neutral_min: float
    supportive_regime_min: float
    headwind_regime_max: float
    factor_library: dict[str, FactorLibraryEntry]
    sector_maps: dict[str, tuple[SectorMapFactorRef, ...]]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SectorMacroContextConfig":
        root = raw.get("sector_macro_context", raw) or {}
        if not isinstance(root, Mapping):
            raise ValueError("sector_macro_context config root must be a mapping")

        status_raw = str(root.get("evidence_status", EvidenceStatus.DIAGNOSTIC.value))
        # v1: only DIAGNOSTIC is accepted (ADR-053).
        if status_raw != EvidenceStatus.DIAGNOSTIC.value:
            raise ValueError(
                f"sector_macro_context.evidence_status must be DIAGNOSTIC in v1, got {status_raw!r}"
            )

        score_labels = root.get("score_labels", {}) or {}
        regime_thr = root.get("regime_thresholds", {}) or {}

        library_raw = root.get("factor_library", {}) or {}
        if not isinstance(library_raw, Mapping) or not library_raw:
            raise ValueError("sector_macro_context.factor_library must be a non-empty mapping")

        factor_library: dict[str, FactorLibraryEntry] = {}
        for name, entry in library_raw.items():
            if not isinstance(entry, Mapping):
                raise ValueError(f"factor_library.{name} must be a mapping")
            kind = str(entry.get("kind", "return_sessions"))
            if kind not in _ALLOWED_KINDS:
                raise ValueError(f"factor_library.{name}.kind unsupported: {kind!r}")
            thr = entry.get("thresholds", {}) or {}
            if kind == "policy_rate_steps":
                supportive = float(thr.get("supportive_min", 1.0))
                headwind = float(thr.get("headwind_max", -1.0))
            else:
                supportive = float(thr.get("supportive_min", 0.05))
                headwind = float(thr.get("headwind_max", -0.05))
            if headwind >= supportive:
                raise ValueError(
                    f"factor_library.{name}: headwind_max ({headwind}) must be < "
                    f"supportive_min ({supportive})"
                )
            lookback_days: int | None = None
            if kind == "policy_rate_steps":
                lookback_days = int(entry.get("lookback_days", _DEFAULT_POLICY_LOOKBACK_DAYS))
                if lookback_days <= 0:
                    raise ValueError(f"factor_library.{name}.lookback_days must be > 0")
            factor_library[str(name)] = FactorLibraryEntry(
                name=str(name),
                series=str(entry.get("series") or "").upper().strip(),
                kind=kind,
                invert=bool(entry.get("invert", False)),
                thresholds=FactorThresholds(
                    supportive_min=supportive,
                    headwind_max=headwind,
                ),
                lookback_days=lookback_days,
            )
            if not factor_library[str(name)].series:
                raise ValueError(f"factor_library.{name}.series is required")

        maps_raw = root.get("sector_maps", {}) or {}
        if not isinstance(maps_raw, Mapping):
            raise ValueError("sector_macro_context.sector_maps must be a mapping")

        sector_maps: dict[str, tuple[SectorMapFactorRef, ...]] = {}
        for group, block in maps_raw.items():
            if not isinstance(block, Mapping):
                raise ValueError(f"sector_maps.{group} must be a mapping")
            refs_raw = block.get("factors") or []
            if not refs_raw:
                raise ValueError(f"sector_maps.{group}.factors must be non-empty")
            refs: list[SectorMapFactorRef] = []
            for item in refs_raw:
                if not isinstance(item, Mapping):
                    raise ValueError(f"sector_maps.{group}.factors entries must be mappings")
                ref = str(item.get("ref") or "")
                if ref not in factor_library:
                    raise ValueError(
                        f"sector_maps.{group} references unknown factor_library key {ref!r}"
                    )
                weight = float(item.get("weight", 0.0))
                if weight <= 0.0:
                    raise ValueError(f"sector_maps.{group} factor {ref!r} weight must be > 0")
                refs.append(SectorMapFactorRef(ref=ref, weight=weight))
            sector_maps[str(group)] = tuple(refs)

        return cls(
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            lookback_sessions=int(root.get("lookback_sessions", 20)),
            min_valid_sessions=int(root.get("min_valid_sessions", 15)),
            min_coverage_to_label=float(root.get("min_coverage_to_label", 0.5)),
            favorable_min=float(score_labels.get("favorable_min", 0.65)),
            neutral_min=float(score_labels.get("neutral_min", 0.35)),
            supportive_regime_min=float(regime_thr.get("supportive_min", 0.65)),
            headwind_regime_max=float(regime_thr.get("headwind_max", 0.35)),
            factor_library=factor_library,
            sector_maps=sector_maps,
        )

    def required_series_tickers(self) -> frozenset[str]:
        """Candle series used by at least one live map (excludes policy_rate_steps)."""
        tickers: set[str] = set()
        for refs in self.sector_maps.values():
            for ref in refs:
                entry = self.factor_library[ref.ref]
                if entry.kind == "return_sessions":
                    tickers.add(entry.series)
        return frozenset(tickers)

    def series_for_group(self, group: str | None) -> tuple[str, ...]:
        """Candle series required for one group map (excludes policy_rate_steps)."""
        if not group:
            return ()
        refs = self.sector_maps.get(group)
        if not refs:
            return ()
        return tuple(
            self.factor_library[r.ref].series
            for r in refs
            if self.factor_library[r.ref].kind == "return_sessions"
        )

    def policy_series_for_group(self, group: str | None) -> tuple[str, ...]:
        """Virtual policy series keys (e.g. BI_RATE) for one group map."""
        if not group:
            return ()
        refs = self.sector_maps.get(group)
        if not refs:
            return ()
        return tuple(
            self.factor_library[r.ref].series
            for r in refs
            if self.factor_library[r.ref].kind == "policy_rate_steps"
        )

    def max_policy_lookback_days_for_group(self, group: str | None) -> int:
        """Max lookback_days among policy factors on a map (default 180)."""
        if not group:
            return _DEFAULT_POLICY_LOOKBACK_DAYS
        refs = self.sector_maps.get(group)
        if not refs:
            return _DEFAULT_POLICY_LOOKBACK_DAYS
        days = [
            self.factor_library[r.ref].lookback_days or _DEFAULT_POLICY_LOOKBACK_DAYS
            for r in refs
            if self.factor_library[r.ref].kind == "policy_rate_steps"
        ]
        return max(days) if days else _DEFAULT_POLICY_LOOKBACK_DAYS

    def all_library_series_tickers(self) -> frozenset[str]:
        """All return_sessions series in the library (for fetch discovery)."""
        return frozenset(
            e.series for e in self.factor_library.values() if e.kind == "return_sessions"
        )


@dataclass(frozen=True)
class SectorMacroContextRequest:
    ticker: str
    snapshot_date: date
    sector_group: str | None  # universes.yaml group key; None if unresolved
    series_candles: Mapping[str, tuple[Candle, ...] | list[Candle]]
    policy_steps: Mapping[str, tuple[PolicyRateStep, ...] | list[PolicyRateStep]] | None = None


class SectorMacroContextEvidenceBuilder:
    """Build SectorMacroContextEvidence from config + preloaded series candles."""

    def __init__(self, config: SectorMacroContextConfig) -> None:
        self._config = config

    @property
    def config(self) -> SectorMacroContextConfig:
        return self._config

    def resolve_sector_group(self, memberships: tuple[str, ...] | list[str]) -> str | None:
        """Pick sector group for macro routing when a ticker has multi-membership.

        Prefer a membership that has a live ``sector_maps`` entry (config key
        order). Falls back to the first membership so unavailable reasons stay
        informative (e.g. sector_map:missing:consumer_goods).
        """
        if not memberships:
            return None
        member_set = set(memberships)
        for group in self._config.sector_maps:
            if group in member_set:
                return group
        return memberships[0]

    def build(self, request: SectorMacroContextRequest) -> SectorMacroContextEvidence:
        try:
            return self._build(request)
        except Exception as exc:  # noqa: BLE001 — fail-soft contract
            return SectorMacroContextEvidence(
                sector_group=request.sector_group,
                as_of_date=request.snapshot_date,
                factors=(),
                composite_score=None,
                macro_regime="UNKNOWN",
                coverage_score=0.0,
                evidence_status=EvidenceStatus.DIAGNOSTIC,
                reasons=(),
                unavailable_reasons=(f"builder_error:{exc}",),
                metadata={"error": str(exc)},
            )

    def _build(self, request: SectorMacroContextRequest) -> SectorMacroContextEvidence:
        cfg = self._config
        group = request.sector_group
        if not group:
            return SectorMacroContextEvidence.unavailable(
                reason="sector_group:unresolved",
                sector_group=None,
                as_of_date=request.snapshot_date,
            )

        map_refs = cfg.sector_maps.get(group)
        if map_refs is None:
            return SectorMacroContextEvidence.unavailable(
                reason=f"sector_map:missing:{group}",
                sector_group=group,
                as_of_date=request.snapshot_date,
            )

        factors: list[MacroFactorScore] = []
        unavailable: list[str] = []
        reasons: list[str] = []
        scored: list[tuple[float, float]] = []  # (score, weight)

        policy_steps_map = request.policy_steps or {}

        for ref in map_refs:
            entry = cfg.factor_library[ref.ref]
            if entry.kind == "policy_rate_steps":
                factor, scored_pair, unavail, reason = _score_policy_factor(
                    entry=entry,
                    weight=ref.weight,
                    steps=policy_steps_map.get(entry.series) or (),
                    as_of=request.snapshot_date,
                    favorable_min=cfg.favorable_min,
                    neutral_min=cfg.neutral_min,
                )
                factors.append(factor)
                if unavail:
                    unavailable.append(unavail)
                if scored_pair is not None:
                    scored.append(scored_pair)
                    reasons.append(reason)
                continue

            candles = request.series_candles.get(entry.series) or ()
            raw_return = _session_return_fraction(
                candles,
                lookback=cfg.lookback_sessions,
                min_valid=cfg.min_valid_sessions,
            )
            if raw_return is None:
                unavailable.append(f"{entry.name}:insufficient_candles:{entry.series}")
                factors.append(
                    MacroFactorScore(
                        name=entry.name,
                        series=entry.series,
                        value=None,
                        score=None,
                        weight=ref.weight,
                        label="UNAVAILABLE",
                        rationale=(
                            f"no/insufficient {entry.series} candles for "
                            f"{cfg.lookback_sessions}d lookback"
                        ),
                    )
                )
                continue

            # invert=false: higher return → higher score (commodity-like).
            # invert=true: higher return → lower score (VIX / risk-like).
            effective = -raw_return if entry.invert else raw_return
            score = _piecewise_score(
                effective,
                supportive_min=entry.thresholds.supportive_min,
                headwind_max=entry.thresholds.headwind_max,
            )
            label = _score_label(score, cfg.favorable_min, cfg.neutral_min)
            invert_note = " (invert risk-like)" if entry.invert else ""
            rationale = (
                f"{entry.series} return {raw_return * 100:+.2f}%{invert_note} "
                f"→ effective {effective * 100:+.2f}% → score {score:.2f}"
            )
            factors.append(
                MacroFactorScore(
                    name=entry.name,
                    series=entry.series,
                    value=raw_return,
                    score=score,
                    weight=ref.weight,
                    label=label,
                    rationale=rationale,
                )
            )
            scored.append((score, ref.weight))
            reasons.append(f"{entry.name}:{label}:{score:.2f}")

        mapped_n = len(map_refs)
        available_n = len(scored)
        coverage = (available_n / mapped_n) if mapped_n > 0 else 0.0

        composite: float | None = None
        if scored:
            w_sum = sum(w for _, w in scored)
            composite = sum(s * w for s, w in scored) / w_sum if w_sum > 0 else None

        macro_regime = _classify_macro_regime(
            composite=composite,
            coverage=coverage,
            min_coverage=cfg.min_coverage_to_label,
            supportive_min=cfg.supportive_regime_min,
            headwind_max=cfg.headwind_regime_max,
        )
        reasons.append(f"macro_regime:{macro_regime}")

        return SectorMacroContextEvidence(
            sector_group=group,
            as_of_date=request.snapshot_date,
            factors=tuple(factors),
            composite_score=round(composite, 4) if composite is not None else None,
            macro_regime=macro_regime,
            coverage_score=round(coverage, 4),
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=tuple(reasons),
            unavailable_reasons=tuple(unavailable),
            metadata={
                "ticker": request.ticker.upper(),
                "mapped_factor_count": mapped_n,
                "available_factor_count": available_n,
            },
        )


def _score_policy_factor(
    *,
    entry: FactorLibraryEntry,
    weight: float,
    steps: tuple[PolicyRateStep, ...] | list[PolicyRateStep],
    as_of: date,
    favorable_min: float,
    neutral_min: float,
) -> tuple[MacroFactorScore, tuple[float, float] | None, str | None, str]:
    """Score a policy_rate_steps factor. Returns (factor, scored_pair, unavail, reason)."""
    from datetime import timedelta

    from src.application.services.policy_rate_steps import (
        filter_steps_on_or_before,
        net_step_delta,
    )

    lookback = entry.lookback_days or _DEFAULT_POLICY_LOOKBACK_DAYS
    window_start = as_of - timedelta(days=lookback)
    in_window = [s for s in filter_steps_on_or_before(steps, as_of) if s.event_date >= window_start]
    net = net_step_delta(in_window)
    if net is None:
        unavail = f"{entry.name}:no_policy_steps:{entry.series}"
        factor = MacroFactorScore(
            name=entry.name,
            series=entry.series,
            value=None,
            score=None,
            weight=weight,
            label="UNAVAILABLE",
            rationale=(
                f"no directional {entry.series} policy steps in {lookback}d lookback "
                f"ending {as_of.isoformat()}"
            ),
        )
        return factor, None, unavail, ""

    # invert=true (bank defensive): hikes (net+) → headwind; cuts (net-) → supportive
    effective = -net if entry.invert else net
    score = _piecewise_score(
        effective,
        supportive_min=entry.thresholds.supportive_min,
        headwind_max=entry.thresholds.headwind_max,
    )
    label = _score_label(score, favorable_min, neutral_min)
    invert_note = " (invert: hike=headwind)" if entry.invert else ""
    rationale = (
        f"{entry.series} net steps {net:+.0f} over {lookback}d{invert_note} "
        f"→ effective {effective:+.0f} → score {score:.2f}"
    )
    reason = f"{entry.name}:{label}:{score:.2f}"
    factor = MacroFactorScore(
        name=entry.name,
        series=entry.series,
        value=net,  # raw net hike/cut count (not a fractional return)
        score=score,
        weight=weight,
        label=label,
        rationale=rationale,
    )
    return factor, (score, weight), None, reason


def _session_return_fraction(
    candles: tuple[Candle, ...] | list[Candle],
    lookback: int,
    min_valid: int,
) -> float | None:
    """Fractional price return over the last `lookback` sessions (L2a semantics)."""
    sorted_c = sorted(candles, key=lambda c: c.date)
    window = sorted_c[-lookback:] if len(sorted_c) >= lookback else sorted_c
    valid = [c for c in window if c.close and float(c.close) > 0]
    if len(valid) < min_valid:
        return None
    ref = float(valid[0].close)
    if ref == 0.0:
        return None
    return (float(valid[-1].close) - ref) / ref


def _piecewise_score(
    effective: float,
    *,
    supportive_min: float,
    headwind_max: float,
) -> float:
    """Map effective return to 0–1. Boundary at headwind/supportive is strict on stress side."""
    if effective >= supportive_min:
        return 1.0
    if effective <= headwind_max:
        return 0.0
    span = supportive_min - headwind_max
    if span <= 0:
        return 0.5
    return (effective - headwind_max) / span


def _score_label(score: float, favorable_min: float, neutral_min: float) -> str:
    if score >= favorable_min:
        return "FAVORABLE"
    if score >= neutral_min:
        return "NEUTRAL"
    return "STRESSED"


def _classify_macro_regime(
    *,
    composite: float | None,
    coverage: float,
    min_coverage: float,
    supportive_min: float,
    headwind_max: float,
) -> str:
    if composite is None or coverage < min_coverage:
        return "UNKNOWN"
    if composite >= supportive_min:
        return "SUPPORTIVE"
    if composite <= headwind_max:
        return "HEADWIND"
    return "NEUTRAL"
