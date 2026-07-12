"""
Tests for group mapping service.
"""

from src.application.services.group_mapping import GroupMappingService

_GROUPS = {
    "TEST_GROUP": {
        "name": "Test Conglomerate",
        "tickers": ["TICK1", "TICK2"],
    },
    "OTHER": {
        "name": "Other Group",
        "tickers": ["TICK3"],
    },
}


class TestGroupMappingService:
    """Test GroupMappingService functionality from a supplied mapping."""

    def test_lookup_from_supplied_mapping(self):
        """Service should look up groups from an already-loaded mapping."""
        service = GroupMappingService(groups=_GROUPS)

        assert service.get_group_id("TICK1") == "TEST_GROUP"
        assert service.get_group_id("tick2") == "TEST_GROUP"  # case-insensitive
        assert service.get_group_id("TICK3") == "OTHER"
        assert service.get_group_id("NONEXISTENT") is None

    def test_get_group_info(self):
        """Service should return correct group info."""
        service = GroupMappingService(groups=_GROUPS)

        info = service.get_group_info("TEST_GROUP")
        assert info["name"] == "Test Conglomerate"
        assert info["tickers"] == ["TICK1", "TICK2"]

        assert service.get_group_info("INVALID") is None

    def test_get_group_tickers(self):
        """Service should return list of tickers for a group."""
        service = GroupMappingService(groups=_GROUPS)

        assert service.get_group_tickers("TEST_GROUP") == ["TICK1", "TICK2"]
        assert service.get_group_tickers("OTHER") == ["TICK3"]
        assert service.get_group_tickers("INVALID") == []

    def test_handle_empty_mapping(self):
        """Service should handle missing/empty mapping gracefully."""
        service = GroupMappingService()
        assert service.get_group_id("ANY") is None
        assert service.get_group_info("ANY") is None
        assert service.get_group_tickers("ANY") == []
