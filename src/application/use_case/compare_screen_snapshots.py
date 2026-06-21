"""
Compare two screener runs: a saved snapshot vs. a fresh result set.

Produces three buckets:
  new      — tickers in fresh results that were NOT in the saved snapshot
  dropped  — tickers in the snapshot that are NOT in fresh results
  changed  — tickers in both; captures rank and score movement

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


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
    def strengthening(self) -> bool:
        delta = self.composite_delta
        return delta is not None and delta >= 3.0 or self.rank_delta >= 3


@dataclass(frozen=True)
class ScreenCompareResult:
    snapshot_name: str
    new_tickers: list[str]       # appeared in fresh results, not in saved
    dropped_tickers: list[str]   # in saved, gone from fresh
    changed: list[SignalChange]  # in both; with movement metrics
    snapshot_count: int          # tickers in saved snapshot
    fresh_count: int             # tickers in fresh results


def compare_screen_snapshots(
    snapshot: list[ScreenSnapshotEntry],
    fresh_tickers: list[str],
    fresh_scores: dict[str, tuple[float, float | None]],  # ticker → (flow_score, composite)
    fresh_ranks: dict[str, int],                           # ticker → 1-based rank
    snapshot_name: str,
) -> ScreenCompareResult:
    """Diff a saved snapshot against a fresh set of screener results.

    Args:
        snapshot:      Saved entries loaded from the repository.
        fresh_tickers: Ordered list of tickers in the new run (rank = index+1).
        fresh_scores:  {ticker: (flow_score, composite_score)} for fresh results.
        fresh_ranks:   {ticker: rank} for fresh results.
        snapshot_name: Display label for the saved snapshot.
    """
    saved_set = {e.ticker for e in snapshot}
    fresh_set = set(fresh_tickers)

    new_tickers = [t for t in fresh_tickers if t not in saved_set]
    dropped_tickers = [e.ticker for e in snapshot if e.ticker not in fresh_set]

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
            old_composite=saved.composite_score,
            new_composite=comp,
            old_flow=saved.flow_score,
            new_flow=flow,
        ))

    return ScreenCompareResult(
        snapshot_name=snapshot_name,
        new_tickers=new_tickers,
        dropped_tickers=dropped_tickers,
        changed=changed,
        snapshot_count=len(snapshot),
        fresh_count=len(fresh_tickers),
    )
