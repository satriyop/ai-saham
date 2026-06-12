"""
Tests for group mapping service.
"""

from pathlib import Path

import pytest
import yaml

from src.application.services.group_mapping import GroupMappingService


@pytest.fixture
def temp_group_config(tmp_path):
    """Create a temporary group config file."""
    config = {
        "groups": {
            "TEST_GROUP": {
                "name": "Test Conglomerate",
                "tickers": ["TICK1", "TICK2"]
            },
            "OTHER": {
                "name": "Other Group",
                "tickers": ["TICK3"]
            }
        }
    }
    config_path = tmp_path / "groups.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return config_path


class TestGroupMappingService:
    """Test GroupMappingService functionality."""

    def test_load_config_and_lookup(self, temp_group_config):
        """Service should load YAML and correctly look up groups."""
        service = GroupMappingService(config_path=temp_group_config)

        assert service.get_group_id("TICK1") == "TEST_GROUP"
        assert service.get_group_id("tick2") == "TEST_GROUP"  # case-insensitive
        assert service.get_group_id("TICK3") == "OTHER"
        assert service.get_group_id("NONEXISTENT") is None

    def test_get_group_info(self, temp_group_config):
        """Service should return correct group info."""
        service = GroupMappingService(config_path=temp_group_config)

        info = service.get_group_info("TEST_GROUP")
        assert info["name"] == "Test Conglomerate"
        assert info["tickers"] == ["TICK1", "TICK2"]

        assert service.get_group_info("INVALID") is None

    def test_get_group_tickers(self, temp_group_config):
        """Service should return list of tickers for a group."""
        service = GroupMappingService(config_path=temp_group_config)

        assert service.get_group_tickers("TEST_GROUP") == ["TICK1", "TICK2"]
        assert service.get_group_tickers("OTHER") == ["TICK3"]
        assert service.get_group_tickers("INVALID") == []

    def test_handle_missing_config(self):
        """Service should handle missing file gracefully."""
        service = GroupMappingService(config_path="nonexistent_file.yaml")
        assert service.get_group_id("ANY") is None
