"""Loader for IDX conglomerate/group mappings (config/idx_groups.yaml).

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.services.group_mapping import GroupInfo, GroupMappingService

DEFAULT_GROUP_MAPPING_PATH = Path("config/idx_groups.yaml")


def load_group_mapping(path: str | Path | None = None) -> dict[str, GroupInfo]:
    """Load group mapping YAML into a group_id -> GroupInfo mapping.

    Group mapping is an optional enrichment: missing files and malformed
    YAML both degrade to an empty mapping rather than raising.
    """
    config_path = Path(path) if path is not None else DEFAULT_GROUP_MAPPING_PATH
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}
    if not data or "groups" not in data:
        return {}
    return data["groups"]


def create_group_mapping_service(path: str | Path | None = None) -> GroupMappingService:
    """Build a GroupMappingService with groups loaded from YAML."""
    return GroupMappingService(groups=load_group_mapping(path))
