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
from src.domain.value_objects.sector_macro_context_evidence import (
    MacroFactorScore,
    SectorMacroContextEvidence,
)

_ALLOWED_KINDS = frozenset({"return_sessions"})


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
            supportive = float(thr.get("supportive_min", 0.05))
            headwind = float(thr.get("headwind_max", -0.05))
            if headwind >= supportive:
                raise ValueError(
                    f"factor_library.{name}: headwind_max ({headwind}) must be < "
                    f"supportive_min ({supportive})"
                )
            factor_library[str(name)] = FactorLibraryEntry(
                name=str(name),
                series=str(entry.get("series") or "").upper().strip(),
                kind=kind,
                invert=bool(entry.get("invert", False)),
                thresholds=FactorThresholds(
                    supportive_min=supportive,
                    headwind_max=headwind,
                ),
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
        """Series used by at least one live sector map (not library-only)."""
        tickers: set[str] = set()
        for refs in self.sector_maps.values():
            for ref in refs:
                entry = self.factor_library[ref.ref]
                tickers.add(entry.series)
        return frozenset(tickers)

    def series_for_group(self, group: str | None) -> tuple[str, ...]:
        """Series required for one universe group map (empty if unmapped)."""
        if not group:
            return ()
        refs = self.sector_maps.get(group)
        if not refs:
            return ()
        return tuple(self.factor_library[r.ref].series for r in refs)

    def all_library_series_tickers(self) -> frozenset[str]:
        return frozenset(e.series for e in self.factor_library.values())


@dataclass(frozen=True)
class SectorMacroContextRequest:
    ticker: str
    snapshot_date: date
    sector_group: str | None  # universes.yaml group key; None if unresolved
    series_candles: Mapping[str, tuple[Candle, ...] | list[Candle]]


class SectorMacroContextEvidenceBuilder:
    """Build SectorMacroContextEvidence from config + preloaded series candles."""

    def __init__(self, config: SectorMacroContextConfig) -> None:
        self._config = config

    @property
    def config(self) -> SectorMacroContextConfig:
        return self._config

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

        for ref in map_refs:
            entry = cfg.factor_library[ref.ref]
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
