"""
Compare two screener runs: a saved snapshot vs. a fresh result set.

Produces buckets:
  new           — tickers in fresh results that were NOT in the saved snapshot
  dropped       — tickers in the snapshot that are NOT in fresh results
  strengthening — tickers in both whose signal materially improved
  weakening     — tickers in both whose signal materially deteriorated
  unchanged     — tickers in both with no material movement

Saved snapshots that used the legacy 0-120 score scale (pre ADR-039) are
detected by value (score > 100) and normalized to the 0-100 scale before
delta calculation. Fresh scores are never normalized.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry

LEGACY_SCALE_DIVISOR = 1.2
STRENGTHENING_COMPOSITE_DELTA = 3.0
STRENGTHENING_RANK_DELTA = 3
WEAKENING_COMPOSITE_DELTA = -3.0
WEAKENING_RANK_DELTA = -3


class MovementStatus(Enum):
    STRENGTHENING = "STRENGTHENING"
    WEAKENING = "WEAKENING"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class SignalChange:
    ticker: str
    old_rank: int
    new_rank: int
    old_composite: float | None
    new_composite: float | None
    old_flow: float
    new_flow: float

    @property
    def rank_delta(self) -> int:
        return self.old_rank - self.new_rank  # positive = moved up

    @property
    def composite_delta(self) -> float | None:
        if self.old_composite is None or self.new_composite is None:
            return None
        return self.new_composite - self.old_composite

    @property
    def flow_delta(self) -> float:
        return self.new_flow - self.old_flow

    @property
    def movement(self) -> MovementStatus:
        """Single-authority, mutually exclusive classification.

        Composite delta is the primary signal. Rank delta is only consulted
        as a fallback when composite delta is missing or itself neutral — it
        never overrides a materially positive/negative composite delta, so a
        ticker cannot land in both strengthening and weakening.
        """
        delta = self.composite_delta
        if delta is not None:
            if delta >= STRENGTHENING_COMPOSITE_DELTA:
                return MovementStatus.STRENGTHENING
            if delta <= WEAKENING_COMPOSITE_DELTA:
                return MovementStatus.WEAKENING

        if self.rank_delta >= STRENGTHENING_RANK_DELTA:
            return MovementStatus.STRENGTHENING
        if self.rank_delta <= WEAKENING_RANK_DELTA:
            return MovementStatus.WEAKENING
        return MovementStatus.UNCHANGED

    @property
    def strengthening(self) -> bool:
        return self.movement is MovementStatus.STRENGTHENING

    @property
    def weakening(self) -> bool:
        return self.movement is MovementStatus.WEAKENING

    @property
    def unchanged(self) -> bool:
        return self.movement is MovementStatus.UNCHANGED


@dataclass(frozen=True)
class ScreenCompareResult:
    snapshot_name: str
    new_tickers: list[str]       # appeared in fresh results, not in saved
    dropped_tickers: list[str]   # in saved, gone from fresh
    changed: list[SignalChange]  # in both; with movement metrics
    snapshot_count: int          # tickers in saved snapshot
    fresh_count: int             # tickers in fresh results
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def strengthening(self) -> list[SignalChange]:
        return [c for c in self.changed if c.strengthening]

    @property
    def weakening(self) -> list[SignalChange]:
        return [c for c in self.changed if c.weakening]

    @property
    def unchanged(self) -> list[SignalChange]:
        return [c for c in self.changed if c.unchanged]


def compare_screen_snapshots(
    snapshot: list[ScreenSnapshotEntry],
    fresh_tickers: list[str],
    fresh_scores: dict[str, tuple[float, float | None]],  # ticker → (accum_score, composite)
    fresh_ranks: dict[str, int],                           # ticker → 1-based rank
    snapshot_name: str,
) -> ScreenCompareResult:
    """Diff a saved snapshot against a fresh set of screener results.

    Args:
        snapshot:      Saved entries loaded from the repository.
        fresh_tickers: Ordered list of tickers in the new run (rank = index+1).
        fresh_scores:  {ticker: (accum_score, signal_score)} for fresh results.
        fresh_ranks:   {ticker: rank} for fresh results.
        snapshot_name: Display label for the saved snapshot.
    """
    saved_set = {e.ticker for e in snapshot}
    fresh_set = set(fresh_tickers)

    new_tickers = [t for t in fresh_tickers if t not in saved_set]
    dropped_tickers = [e.ticker for e in snapshot if e.ticker not in fresh_set]

    is_legacy_scale = any(
        (e.accum_score is not None and e.accum_score > 100)
        or (e.signal_score is not None and e.signal_score > 100)
        for e in snapshot
    )
    warnings: tuple[str, ...] = ()
    if is_legacy_scale:
        warnings = (
            f"Saved snapshot '{snapshot_name}' uses legacy 0-120 score scale; "
            "values normalized to 0-100 before comparison.",
        )

    def _normalize(value: float | None) -> float | None:
        if value is None or not is_legacy_scale:
            return value
        return value / LEGACY_SCALE_DIVISOR

    saved_by_ticker = {e.ticker: e for e in snapshot}
    changed: list[SignalChange] = []
    for ticker in fresh_tickers:
        if ticker not in saved_by_ticker:
            continue
        saved = saved_by_ticker[ticker]
        flow, comp = fresh_scores.get(ticker, (0.0, None))
        changed.append(SignalChange(
            ticker=ticker,
            old_rank=saved.rank,
            new_rank=fresh_ranks.get(ticker, 999),
            old_composite=_normalize(saved.signal_score),
            new_composite=comp,
            old_flow=_normalize(saved.accum_score),
            new_flow=flow,
        ))

    return ScreenCompareResult(
        snapshot_name=snapshot_name,
        new_tickers=new_tickers,
        dropped_tickers=dropped_tickers,
        changed=changed,
        snapshot_count=len(snapshot),
        fresh_count=len(fresh_tickers),
        warnings=warnings,
    )
