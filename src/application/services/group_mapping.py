"""
Group mapping service.

Loads IDX conglomerate and group mappings from YAML and provides
lookup methods for sentiment propagation.

Layer: Application (Service)
"""

from pathlib import Path
from typing import TypedDict

import yaml


class GroupInfo(TypedDict):
    name: str
    tickers: list[str]


class GroupMappingService:
    """Service for looking up stock group/conglomerate affiliations.

    Loads mappings from a static YAML file (default: config/idx_groups.yaml).
    """

    def __init__(self, config_path: str | Path = "config/idx_groups.yaml"):
        """Initialize service by loading config.

        Args:
            config_path: Path to the groups YAML file
        """
        self._config_path = Path(config_path)
        self._groups: dict[str, GroupInfo] = {}
        self._ticker_to_group: dict[str, str] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load and parse the YAML config file."""
        if not self._config_path.exists():
            return

        try:
            with open(self._config_path, "r") as f:
                data = yaml.safe_load(f)

            if not data or "groups" not in data:
                return

            self._groups = data["groups"]

            # Build reverse lookup: ticker -> group_id
            for group_id, info in self._groups.items():
                for ticker in info.get("tickers", []):
                    self._ticker_to_group[ticker.upper()] = group_id

        except Exception:
            # Fail silently - group mapping is an optional enrichment
            pass

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
