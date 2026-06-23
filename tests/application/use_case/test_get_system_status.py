"""Tests for GetSystemStatusUseCase."""

from datetime import date, timedelta

from src.application.use_case.get_system_status import GetSystemStatusUseCase
from src.domain.ports.system_status_provider import (
    ProviderStatusDto,
    SystemStatusProvider,
    TableFreshnessDto,
)


class MockSystemStatusProvider(SystemStatusProvider):

    def check_provider_health(self):
        return [
            ProviderStatusDto(name="Test API", ok=True, label="200 OK", ms=0.1)
        ]

    def get_data_freshness(self):
        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        current_str = (date.today() - timedelta(days=3)).isoformat()
        stale_str = (date.today() - timedelta(days=10)).isoformat()

        return [
            TableFreshnessDto(
                table="table_today", source="test", latest=today_str, count=100
            ),
            TableFreshnessDto(
                table="table_yesterday",
                source="test",
                latest=yesterday_str,
                count=200,
            ),
            TableFreshnessDto(
                table="table_current",
                source="test",
                latest=current_str,
                count=300,
            ),
            TableFreshnessDto(
                table="table_stale", source="test", latest=stale_str, count=400
            ),
            TableFreshnessDto(
                table="table_empty", source="test", latest=None, count=0
            ),
        ]


def test_get_system_status_use_case():
    provider = MockSystemStatusProvider()
    use_case = GetSystemStatusUseCase(provider)
    response = use_case.execute()

    assert len(response.providers) == 1
    assert response.providers[0].name == "Test API"

    freshness_map = {item.table: item for item in response.freshness}

    assert freshness_map["table_today"].status == "today"
    assert freshness_map["table_today"].days_behind == 0

    assert freshness_map["table_yesterday"].status == "yesterday"
    assert freshness_map["table_yesterday"].days_behind == 1

    assert freshness_map["table_current"].status == "current"
    assert freshness_map["table_current"].days_behind == 3

    assert freshness_map["table_stale"].status == "stale"
    assert freshness_map["table_stale"].days_behind == 10

    assert freshness_map["table_empty"].status == "unknown"
