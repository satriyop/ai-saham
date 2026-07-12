"""Provider protocol for universe catalog operations.

Layer: Application
"""

from typing import Protocol


class UniverseCatalogProvider(Protocol):
    """Protocol for fetching universe data from a catalog source."""

    def list_available(self) -> dict[str, tuple[int | str, int]]:
        """Return discovered universe_key -> (subsector_id, sector_number) map."""
        ...

    def fetch(self, universe_key: str) -> list[str]:
        """Return sorted ticker list for a universe key."""
        ...

    def get(self, url: str) -> dict | None:
        """Raw GET request for inspect/discovery endpoints."""
        ...
