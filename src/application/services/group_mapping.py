"""
Group mapping service.

Provides lookup methods for IDX conglomerate/group affiliations from an
already-loaded groups mapping, for sentiment propagation.

Layer: Application (Service)
"""

from typing import TypedDict


class GroupInfo(TypedDict):
    name: str
    tickers: list[str]


class GroupMappingService:
    """Service for looking up stock group/conglomerate affiliations.

    Consumes an already-loaded groups mapping (group_id -> GroupInfo).
    Infrastructure loaders own reading the backing YAML file.
    """

    def __init__(self, groups: dict[str, GroupInfo] | None = None) -> None:
        """Initialize service from a pre-loaded groups mapping.

        Args:
            groups: Mapping of group_id -> GroupInfo, or None/empty when
                group data is unavailable.
        """
        self._groups: dict[str, GroupInfo] = groups or {}
        self._ticker_to_group: dict[str, str] = {}
        for group_id, info in self._groups.items():
            for ticker in info.get("tickers", []):
                self._ticker_to_group[ticker.upper()] = group_id

    def get_group_id(self, ticker: str) -> str | None:
        """Get the group ID for a given ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Group ID (e.g., 'BUMN', 'BARITO') or None if not found
        """
        return self._ticker_to_group.get(ticker.upper())

    def get_group_info(self, group_id: str) -> GroupInfo | None:
        """Get full information for a group.

        Args:
            group_id: The ID of the group

        Returns:
            GroupInfo dict or None if not found
        """
        return self._groups.get(group_id)

    def get_group_tickers(self, group_id: str) -> list[str]:
        """Get all tickers belonging to a group.

        Args:
            group_id: The ID of the group

        Returns:
            List of ticker symbols
        """
        info = self.get_group_info(group_id)
        return info.get("tickers", []) if info else []
