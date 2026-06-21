"""
ValuationMetrics — per-ticker valuation ratios from Stockbit /valuation endpoint.

Stores raw {metric_id: value} pairs. Known IDs are exposed as named properties;
unknown IDs remain accessible via the raw dict for forward compatibility.

Empirically observed metric IDs (BBCA, 2026-06-20):
  12635 → P/E (current)   — 20.96 for BBCA
  13200 → EPS TTM (IDR)   — 471.10 for BBCA

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Hard-coded lookup built from empirical observation. Add new IDs as discovered
# via `saham fetch stockbit spy` sessions.
KNOWN_METRIC_LABELS: dict[int, str] = {
    12635: "P/E",
    13200: "EPS (TTM)",
    12623: "+1σ PE (1Y)",
    12626: "+2σ PE (1Y)",
}


@dataclass(frozen=True)
class ValuationMetrics:
    """Per-ticker valuation ratio snapshot.

    raw: dict mapping Stockbit metric IDs to float values. IDs with value 0.0
    are filtered on ingest (they are placeholders, id=0 or zero values).
    """

    ticker: str
    fetched_at: datetime
    raw: dict[int, float] = field(default_factory=dict)

    @property
    def pe_current(self) -> float | None:
        return self.raw.get(12635)

    @property
    def eps_ttm(self) -> float | None:
        return self.raw.get(13200)

    @property
    def pe_plus1_sd(self) -> float | None:
        return self.raw.get(12623)

    @property
    def pe_plus2_sd(self) -> float | None:
        return self.raw.get(12626)

    @property
    def labeled(self) -> list[tuple[str, float]]:
        """Return (label, value) pairs for all known metric IDs in raw."""
        result = []
        for metric_id, label in KNOWN_METRIC_LABELS.items():
            if metric_id in self.raw:
                result.append((label, self.raw[metric_id]))
        return result

    @property
    def is_empty(self) -> bool:
        return not self.raw
