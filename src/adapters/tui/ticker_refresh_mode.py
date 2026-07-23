"""Ticker Decision Workbench analysis refresh mode.

Owns the single, exact mapping between a user-facing analysis mode and the
``SwingAnalysisWorkflowRequest`` provider flags. Keeping the mapping in one typed
place means the screen never invents its own flag combination and the mapping can
be asserted directly by tests.

Layer: Adapter
"""

from __future__ import annotations

from enum import Enum


class TickerRefreshMode(Enum):
    """How an explicit Run may touch providers.

    ``flags`` returns ``(auto_refresh, force_refresh)`` exactly as required by the
    roadmap contract:

    - Cached only    -> (False, False): never contacts a provider.
    - Update if stale -> (True,  False): refresh when local data is stale.
    - Force update   -> (True,  True):  always refresh from the provider.
    """

    CACHED_ONLY = "CACHED_ONLY"
    UPDATE_IF_STALE = "UPDATE_IF_STALE"
    FORCE_UPDATE = "FORCE_UPDATE"

    @property
    def flags(self) -> tuple[bool, bool]:
        return _FLAGS[self]

    @property
    def auto_refresh(self) -> bool:
        return self.flags[0]

    @property
    def force_refresh(self) -> bool:
        return self.flags[1]

    @property
    def touches_provider(self) -> bool:
        return self.auto_refresh

    @property
    def label(self) -> str:
        return _LABELS[self]


_FLAGS: dict[TickerRefreshMode, tuple[bool, bool]] = {
    TickerRefreshMode.CACHED_ONLY: (False, False),
    TickerRefreshMode.UPDATE_IF_STALE: (True, False),
    TickerRefreshMode.FORCE_UPDATE: (True, True),
}

_LABELS: dict[TickerRefreshMode, str] = {
    TickerRefreshMode.CACHED_ONLY: "Cached only",
    TickerRefreshMode.UPDATE_IF_STALE: "Update if stale",
    TickerRefreshMode.FORCE_UPDATE: "Force update",
}
