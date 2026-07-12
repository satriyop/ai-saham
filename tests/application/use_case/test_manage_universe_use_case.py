"""Tests for manage universe use cases."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.application.dto.universe_management import UniverseUpdateResult
from src.application.services.universe_config_store import UniverseConfigStore
from src.application.use_case.manage_universe_use_case import (
    CreateUniverseUseCase,
    InspectUniverseUseCase,
    UpdateUniverseUseCase,
)


class MockProvider:
    """Mock provider for testing."""

    def __init__(self) -> None:
        self._available: dict[str, tuple[int | str, int]] = {
            "lq45": (550, 88),
            "finance": (82, 70),
        }
        self._get_responses: dict[str, dict[str, Any] | None] = {}

    def list_available(self) -> dict[str, tuple[int | str, int]]:
        return self._available

    def fetch(self, key: str) -> list[str]:
        if key == "lq45":
            return ["BBCA", "BBRI", "BMRI"]
        if key == "finance":
            return ["BBCA", "BBRI", "BDMN"]
        return []

    def get(self, url: str) -> dict[str, Any] | None:
        for pattern, resp in self._get_responses.items():
            if pattern in url:
                return resp
        return None

    def set_get_response(self, pattern: str, response: dict[str, Any] | None) -> None:
        self._get_responses[pattern] = response


class MockSleep:
    """Mock sleep that records calls."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, secs: float) -> None:
        self.calls.append(secs)


def universe_type(key: str) -> str:
    """Mock universe type resolver."""
    types = {
        "lq45": "broad",
        "finance": "sectoral",
    }
    return types.get(key, "unknown")


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    return tmp_path / "config" / "universes.yaml"


@pytest.fixture
def config_store(tmp_config: Path) -> UniverseConfigStore:
    return UniverseConfigStore(tmp_config)


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
def sleep() -> MockSleep:
    return MockSleep()


# --- UpdateUniverseUseCase tests ---


def test_update_discover_returns_items(
    provider: MockProvider, config_store: UniverseConfigStore, sleep: MockSleep
):
    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    result = use_case.execute(
        universe_name=None, discover=True, today=date(2026, 6, 24)
    )

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0].key == "finance"
    assert result[0].universe_type == "sectoral"
    assert result[0].subsector_id == 82
    assert result[0].sector_id == 70
    assert result[1].key == "lq45"
    assert result[1].universe_type == "broad"


def test_update_single_universe(
    provider: MockProvider, config_store: UniverseConfigStore, sleep: MockSleep
):
    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    result = use_case.execute(
        universe_name="lq45", discover=False, today=date(2026, 6, 24)
    )

    assert isinstance(result, UniverseUpdateResult)
    assert len(result.updated) == 1
    assert result.updated[0].key == "lq45"
    assert result.updated[0].universe_type == "broad"
    assert result.updated[0].tickers == ("BBCA", "BBRI", "BMRI")
    assert result.updated[0].previous_count == 0
    assert result.updated[0].delta == 3
    assert config_store.config_path.exists()


def test_update_unknown_universe_fails(
    provider: MockProvider, config_store: UniverseConfigStore, sleep: MockSleep
):
    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    with pytest.raises(ValueError, match="Unknown universe"):
        use_case.execute(
            universe_name="unknown", discover=False, today=date(2026, 6, 24)
        )


def test_update_custom_universe_preserves_metadata(
    tmp_path: Path, provider: MockProvider, sleep: MockSleep
):
    config_path = tmp_path / "config" / "universes.yaml"
    config_store = UniverseConfigStore(config_path)

    # Seed custom universe
    import yaml

    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "bank": {
            "tickers": ["BBCA"],
            "updated": "2026-06-20",
            "sector_id": 3,
            "subsector_id": 20,
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(initial, f)

    provider.set_get_response(
        "subsector/20/company",
        {
            "data": {
                "companies": [
                    {"ticker": "BBCA", "name": "Bank BCA"},
                    {"ticker": "BBRI", "name": "Bank BRI"},
                    {"ticker": "BMRI", "name": "Bank Mandiri"},
                ]
            },
        },
    )

    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    result = use_case.execute(
        universe_name="bank", discover=False, today=date(2026, 6, 24)
    )

    assert len(result.updated) == 1
    assert result.updated[0].tickers == ("BBCA", "BBRI", "BMRI")

    # Verify metadata preserved
    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert data["bank"]["sector_id"] == 3
    assert data["bank"]["subsector_id"] == 20
    assert data["bank"]["updated"] == "2026-06-24"


def test_update_all_includes_custom_universes(
    tmp_path: Path, provider: MockProvider, sleep: MockSleep
):
    config_path = tmp_path / "config" / "universes.yaml"
    config_store = UniverseConfigStore(config_path)

    import yaml

    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "bank": {
            "tickers": ["BBCA"],
            "updated": "2026-06-20",
            "sector_id": 3,
            "subsector_id": 20,
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(initial, f)

    provider.set_get_response(
        "subsector/20/company",
        {
            "data": {
                "companies": [
                    {"ticker": "BBCA", "name": "Bank BCA"},
                    {"ticker": "BBNI", "name": "Bank BNI"},
                ]
            },
        },
    )

    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    use_case.execute(universe_name=None, discover=False, today=date(2026, 6, 24))

    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert data["bank"]["tickers"] == ["BBCA", "BBNI"]
    assert data["bank"]["sector_id"] == 3
    assert data["bank"]["subsector_id"] == 20


def test_update_custom_with_subsector_fetches_only_that(
    provider: MockProvider,
    config_store: UniverseConfigStore,
    sleep: MockSleep
):
    import yaml
    config_store.config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "custom1": {
            "tickers": [],
            "updated": "2026-01-01",
            "sector_id": 1,
            "subsector_id": 10,
        }
    }
    with open(config_store.config_path, "w") as f:
        yaml.dump(initial, f)

    provider.set_get_response("subsector/10/company", {
        "data": {"companies": [{"ticker": "MYOR"}, {"ticker": "icbp"}]}
    })

    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    result = use_case.execute(
        universe_name="custom1", discover=False, today=date(2026, 6, 24)
    )

    assert result.updated[0].tickers == ("ICBP", "MYOR")


def test_update_custom_without_subsector_paces_between_subsectors(
    tmp_path: Path,
    provider: MockProvider,
    sleep: MockSleep
):
    config_path = tmp_path / "config" / "universes.yaml"
    config_store = UniverseConfigStore(config_path)

    import yaml
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "custom_sector": {
            "tickers": [],
            "updated": "2026-01-01",
            "sector_id": 1,
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(initial, f)

    provider.set_get_response("sectors/1/subsectors", {
        "data": {"subsectors": [
            {"id": 10, "name": "Food & Beverage"},
            {"id": 11, "name": "Tobacco"},
        ]}
    })
    provider.set_get_response("subsector/10/company", {"data": {"companies": [{"ticker": "ICBP"}]}})
    provider.set_get_response("subsector/11/company", {"data": {"companies": [{"ticker": "GGRM"}]}})

    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    result = use_case.execute(
        universe_name="custom_sector", discover=False, today=date(2026, 6, 24)
    )

    assert len(sleep.calls) == 1
    assert sleep.calls[0] == 0.2
    assert result.updated[0].tickers == ("GGRM", "ICBP")


def test_update_custom_subsector_fetch_none_fails_that_universe(
    tmp_path: Path,
    provider: MockProvider,
    sleep: MockSleep
):
    config_path = tmp_path / "config" / "universes.yaml"
    config_store = UniverseConfigStore(config_path)

    import yaml
    config_path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "custom_sector": {
            "tickers": [],
            "updated": "2026-01-01",
            "sector_id": 1,
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(initial, f)

    provider.set_get_response("sectors/1/subsectors", {
        "data": {"subsectors": [
            {"id": 10, "name": "Food & Beverage"},
            {"id": 11, "name": "Tobacco"},
        ]}
    })
    provider.set_get_response("subsector/10/company", {"data": {"companies": [{"ticker": "ICBP"}]}})
    provider.set_get_response("subsector/11/company", None)  # fail second

    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    result = use_case.execute(
        universe_name="custom_sector", discover=False, today=date(2026, 6, 24)
    )

    # Should have failed because one subsector returned None
    assert "custom_sector" in result.failed


def test_update_all_failed_returns_result(
    provider: MockProvider,
    config_store: UniverseConfigStore,
    sleep: MockSleep
):
    use_case = UpdateUniverseUseCase(
        provider, config_store, sleep=sleep, universe_type=universe_type
    )
    # Use a universe that returns empty results
    provider._available = {"empty_universe": (999, 99)}
    result = use_case.execute(
        universe_name="empty_universe", discover=False, today=date(2026, 6, 24)
    )

    # Should return result with failed, not raise
    assert isinstance(result, UniverseUpdateResult)
    assert len(result.updated) == 0
    assert "empty_universe" in result.failed


# --- CreateUniverseUseCase tests ---


def test_create_with_subsector(
    provider: MockProvider,
    config_store: UniverseConfigStore,
    sleep: MockSleep
):
    provider.set_get_response("subsector/10/company", {
        "data": {"companies": [
            {"ticker": "MYOR", "name": "Mayora Indah"},
            {"ticker": "icbp", "name": "Indofood CBP"},
        ]}
    })

    use_case = CreateUniverseUseCase(
        provider, config_store, sleep=sleep
    )
    result = use_case.execute(
        name="food_bev", sector_id=1, subsector_id=10, today=date(2026, 6, 24)
    )

    assert result.universe_name == "food_bev"
    assert result.tickers == ("ICBP", "MYOR")
    assert result.sector_id == 1
    assert result.subsector_id == 10
    assert config_store.config_path.exists()

    import yaml
    with open(config_store.config_path) as f:
        data = yaml.safe_load(f)
    assert data["food_bev"]["tickers"] == ["ICBP", "MYOR"]
    assert data["food_bev"]["sector_id"] == 1
    assert data["food_bev"]["subsector_id"] == 10


def test_create_sector_level_deduplicates_and_sorts(
    provider: MockProvider,
    config_store: UniverseConfigStore,
    sleep: MockSleep
):
    provider.set_get_response("sectors/1/subsectors", {
        "data": {"subsectors": [
            {"id": 10, "name": "Food & Beverage"},
            {"id": 11, "name": "Tobacco"},
        ]}
    })
    provider.set_get_response("subsector/10/company", {
        "data": {"companies": [
            {"ticker": "ICBP", "name": "Indofood CBP"},
            {"ticker": "INDF", "name": "Indofood Sukses"},
        ]}
    })
    provider.set_get_response("subsector/11/company", {
        "data": {"companies": [
            {"ticker": "GGRM", "name": "Gudang Garam"},
            {"ticker": "ICBP", "name": "Indofood CBP"},  # duplicate
        ]}
    })

    use_case = CreateUniverseUseCase(
        provider, config_store, sleep=sleep
    )
    result = use_case.execute(
        name="consumer_primer_full", sector_id=1, subsector_id=None, today=date(2026, 6, 24)
    )

    assert result.tickers == ("GGRM", "ICBP", "INDF")
    assert result.subsector_id is None
    assert len(sleep.calls) == 1
    assert sleep.calls[0] == 0.2


def test_create_sector_level_fail_fast_no_config_write(
    tmp_path: Path,
    provider: MockProvider,
    sleep: MockSleep
):
    config_path = tmp_path / "config" / "universes.yaml"
    config_store = UniverseConfigStore(config_path)

    provider.set_get_response("sectors/1/subsectors", {
        "data": {"subsectors": [
            {"id": 10, "name": "Food & Beverage"},
            {"id": 11, "name": "Tobacco"},
        ]}
    })
    provider.set_get_response("subsector/10/company", {"data": {"companies": [{"ticker": "ICBP"}]}})
    provider.set_get_response("subsector/11/company", None)  # fail

    use_case = CreateUniverseUseCase(
        provider, config_store, sleep=sleep
    )
    with pytest.raises(ValueError, match="Aborting transaction to keep config safe"):
        use_case.execute(
            name="should_fail", sector_id=1, subsector_id=None, today=date(2026, 6, 24)
        )

    # Config file should not exist
    assert not config_path.exists()


def test_create_name_normalized(
    provider: MockProvider,
    config_store: UniverseConfigStore,
    sleep: MockSleep
):
    provider.set_get_response("subsector/10/company", {"data": {"companies": [{"ticker": "BBCA"}]}})

    use_case = CreateUniverseUseCase(
        provider, config_store, sleep=sleep
    )
    result = use_case.execute(
        name="  Food_Bev  ", sector_id=1, subsector_id=10, today=date(2026, 6, 24)
    )

    assert result.universe_name == "food_bev"


def test_create_empty_tickers_fails(
    provider: MockProvider,
    config_store: UniverseConfigStore,
    sleep: MockSleep
):
    provider.set_get_response("subsector/10/company", {"data": {"companies": []}})

    use_case = CreateUniverseUseCase(
        provider, config_store, sleep=sleep
    )
    with pytest.raises(ValueError, match="No companies found"):
        use_case.execute(name="empty", sector_id=1, subsector_id=10, today=date(2026, 6, 24))


# --- InspectUniverseUseCase tests ---


def test_inspect_sectors(provider: MockProvider):
    provider.set_get_response("emitten/sectors", {
        "data": {"sectors": [
            {"id": 70, "name": "Finance", "total_company": 10},
            {"id": 88, "name": "Indices", "total_company": 5},
        ]}
    })

    use_case = InspectUniverseUseCase(provider)
    result = use_case.execute(sector_id=None, subsector_id=None, with_count=False)

    assert result.title == "STOCKBIT SECTORS"
    assert len(result.rows) == 2
    assert result.rows[0].id == "70"
    assert result.rows[0].name == "Finance"
    assert result.rows[0].count == "10"
    assert "Known useful IDs: 88=Broad Indices  70=Sectoral Indices" in result.tip_lines[1]


def test_inspect_subsectors(provider: MockProvider):
    provider.set_get_response("emitten/sectors/5/subsectors", {
        "data": {"subsectors": [
            {"id": 10, "name": "Bank", "total_company": 8},
            {"id": 11, "name": "Insurance", "total_company": 2},
        ]}
    })

    use_case = InspectUniverseUseCase(provider)
    result = use_case.execute(sector_id=5, subsector_id=None, with_count=False)

    assert result.title == "SUBSECTORS OF SECTOR 5"
    assert len(result.rows) == 2
    assert result.rows[0].id == "10"
    assert result.rows[0].count == "8"


def test_inspect_subsectors_with_count_fetches_counts(provider: MockProvider):
    provider.set_get_response("emitten/sectors/5/subsectors", {
        "data": {"subsectors": [
            {"id": 10, "name": "Bank", "total_company": 8},
            {"id": 11, "name": "Insurance"},
        ]}
    })
    provider.set_get_response("emitten/v3/sector/5/subsector/11/company", {
        "data": {"companies": [{"ticker": "TEST1"}, {"ticker": "TEST2"}]}
    })

    use_case = InspectUniverseUseCase(provider)
    result = use_case.execute(sector_id=5, subsector_id=None, with_count=True)

    # First has count already, second should be filled
    row_10 = next(r for r in result.rows if r.id == "10")
    row_11 = next(r for r in result.rows if r.id == "11")
    assert row_10.count == "8"
    assert row_11.count == "2"


def test_inspect_companies(provider: MockProvider):
    provider.set_get_response("emitten/v3/sector/5/subsector/49/company", {
        "data": {"companies": [
            {"ticker": "BBCA", "name": "Bank BCA"},
            {"code": "BBRI", "company_name": "Bank BRI"},
        ]}
    })

    use_case = InspectUniverseUseCase(provider)
    result = use_case.execute(sector_id=5, subsector_id=49, with_count=False)

    assert result.title == "COMPANIES IN SUBSECTOR 49 (Sector 5)"
    assert len(result.rows) == 2
    assert result.total == 2
    assert result.rows[0].id == "BBCA"
    assert result.rows[1].id == "BBRI"


def test_inspect_subsector_without_sector_fails():
    provider = MockProvider()
    use_case = InspectUniverseUseCase(provider)
    with pytest.raises(ValueError, match="required when specifying"):
        use_case.execute(sector_id=None, subsector_id=10, with_count=False)
