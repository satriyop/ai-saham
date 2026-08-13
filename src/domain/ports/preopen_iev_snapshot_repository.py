"""
Narrow read port for pre-open IEV snapshot coverage.

The IEV store predates the ports convention: ``SQLiteIEVRepository`` is concrete
infrastructure with no interface, and application code may not import it
(enforced by ``tests/architecture/test_layer_boundaries.py``). Rather than widen
the readiness use case's surface to the whole repository, this port exposes the
single question the pre-flight actually asks.

Deliberately a count and not the rows: the readiness check needs to know whether
the scheduled fetch produced anything, not what it produced. Handing the use
case an IEV row type would drag an infrastructure dataclass inward for no gain.

Layer: Domain (port)
"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class PreOpenIevSnapshotCountPort(Protocol):
    def count_snapshot_rows(self, snapshot_date: date) -> int:
        """Number of IEV rows stored for one session date. 0 when none."""
        ...
