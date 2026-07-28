"""
Port: read the NCP-locked pre-open IEV baseline.

Layer: Application (port)
AI usage: None

The daily briefing surfaces the pre-open decision context stored in the learning
corpus. To show the locked-input signal it needs the 08:56 NCP-locked IEV baseline
per ticker, so it can compute `delta_iev = decision_iev - baseline` — the same
locked-input delta the `research pre-open capture` cron uses (see ADR-048/ADR-049
and install_cron.sh). The port returns primitives so no infrastructure type crosses
the boundary.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class IEVBaselineReadPort(Protocol):
    """Read the NCP-locked (08:56) pre-open IEV baseline per ticker."""

    def ncp_baseline_iev(self, snapshot_date: date) -> dict[str, int]:
        """Return {ticker: baseline_iev} from the latest 08:56 NCP-locked batch.

        Empty dict when no locked baseline exists for the date.
        """
        ...
