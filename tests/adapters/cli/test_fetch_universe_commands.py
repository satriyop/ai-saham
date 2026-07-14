import time
from pathlib import Path

import yaml
from typer.testing import CliRunner

import src.infrastructure.browser.stockbit_api_client as _stockbit_api_client
import src.infrastructure.composition.stockbit_session_factory as _session_svc
from src.adapters.cli.main import app
from src.application.services.stockbit_session import StockbitSession

runner = CliRunner()


def test_universe_create_help():
    result = runner.invoke(app, ["fetch", "universe", "create", "--help"])
    assert result.exit_code == 0
    assert "Create a custom universe from a Stockbit" in result.stdout


def _mock_authenticated_session(monkeypatch):
    """Patch get_stockbit_session() to return an authenticated session with a fake api_client."""
    _fake_client = object.__new__(_stockbit_api_client.StockbitApiClient)
    monkeypatch.setattr(
        _session_svc, "get_stockbit_session",
        lambda stockbit_config=None: StockbitSession(api_client=_fake_client, authenticated=True),
    )
    return _fake_client


class MockUniverseProvider:
    def __init__(self, api_client, stockbit_config=None):
        pass

    def list_available(self):
        return {
            "lq45": (550, 88),
            "finance": (82, 70),
        }

    def fetch(self, key):
        if key == "lq45":
            return ["BBCA", "BBRI", "BMRI"]
        elif key == "finance":
            return ["BBCA", "BBRI", "BDMN"]
        return []


def test_universe_create_with_subsector(monkeypatch, tmp_path: Path):
    # Setup stockbit profile dir
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    # Mock Stockbit session
    _fake_client = _mock_authenticated_session(monkeypatch)

    # Mock API call
    def mock_api_get(self, url: str, params=None):
        if "subsector/10/company" in url:
            return {
                "data": {
                    "companies": [
                        {"ticker": "MYOR", "name": "Mayora Indah"},
                        {"ticker": "icbp", "name": "Indofood CBP"},
                    ]
                }
            }
        return None

    monkeypatch.setattr(_stockbit_api_client.StockbitApiClient, "get", mock_api_get)

    config_file = tmp_path / "config" / "universes.yaml"
    result = runner.invoke(
        app,
        [
            "fetch",
            "universe",
            "create",
            "food_bev",
            "--sector",
            "1",
            "--subsector",
            "10",
            "--config",
            str(config_file),
        ],
    )

    assert result.exit_code == 0
    assert "CUSTOM UNIVERSE CREATED & SYNCED" in result.stdout
    assert config_file.exists()

    with open(config_file) as f:
        data = yaml.safe_load(f)

    assert "food_bev" in data
    assert data["food_bev"]["tickers"] == ["ICBP", "MYOR"]
    assert data["food_bev"]["sector_id"] == 1
    assert data["food_bev"]["subsector_id"] == 10


def test_universe_create_sector_level(monkeypatch, tmp_path: Path):
    # Setup stockbit profile dir
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    # Mock Stockbit session
    _fake_client = _mock_authenticated_session(monkeypatch)

    # Mock API calls and capture sleep times
    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda secs: sleep_calls.append(secs))

    def mock_api_get(self, url: str, params=None):
        if "sectors/1/subsectors" in url:
            return {
                "data": {
                    "subsectors": [
                        {"id": 10, "name": "Food & Beverage"},
                        {"id": 11, "name": "Tobacco"},
                    ]
                }
            }
        elif "subsector/10/company" in url:
            return {
                "data": {
                    "companies": [
                        {"ticker": "ICBP", "name": "Indofood CBP"},
                        {"ticker": "INDF", "name": "Indofood Sukses"},
                    ]
                }
            }
        elif "subsector/11/company" in url:
            return {
                "data": {
                    "companies": [
                        {"ticker": "GGRM", "name": "Gudang Garam"},
                        {"ticker": "ICBP", "name": "Indofood CBP"},  # duplicate ticker
                    ]
                }
            }
        return None

    monkeypatch.setattr(_stockbit_api_client.StockbitApiClient, "get", mock_api_get)

    config_file = tmp_path / "config" / "universes.yaml"
    result = runner.invoke(
        app,
        [
            "fetch",
            "universe",
            "create",
            "consumer_primer_full",
            "--sector",
            "1",
            "--config",
            str(config_file),
        ],
    )

    assert result.exit_code == 0
    assert "CUSTOM UNIVERSE CREATED & SYNCED" in result.stdout
    assert config_file.exists()

    with open(config_file) as f:
        data = yaml.safe_load(f)

    assert "consumer_primer_full" in data
    # Unique, sorted, uppercase
    assert data["consumer_primer_full"]["tickers"] == ["GGRM", "ICBP", "INDF"]
    assert data["consumer_primer_full"]["sector_id"] == 1
    assert "subsector_id" not in data["consumer_primer_full"]

    # Verify sleep pacing occurred between subsectors (1 sleep call since there are 2 subsectors)
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 0.2


def test_universe_create_sector_level_fail_fast(monkeypatch, tmp_path: Path):
    # Setup stockbit profile dir
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    # Mock Stockbit session
    _fake_client = _mock_authenticated_session(monkeypatch)

    # Mock API calls where the second subsector fetch fails
    def mock_api_get(self, url: str, params=None):
        if "sectors/1/subsectors" in url:
            return {
                "data": {
                    "subsectors": [
                        {"id": 10, "name": "Food & Beverage"},
                        {"id": 11, "name": "Tobacco"},
                    ]
                }
            }
        elif "subsector/10/company" in url:
            return {
                "data": {
                    "companies": [
                        {"ticker": "ICBP", "name": "Indofood CBP"},
                    ]
                }
            }
        elif "subsector/11/company" in url:
            return None
        return None

    monkeypatch.setattr(_stockbit_api_client.StockbitApiClient, "get", mock_api_get)

    config_file = tmp_path / "config" / "universes.yaml"
    result = runner.invoke(
        app,
        [
            "fetch",
            "universe",
            "create",
            "should_fail",
            "--sector",
            "1",
            "--config",
            str(config_file),
        ],
    )

    assert result.exit_code == 1
    expected_err = "Error: Failed to fetch data for sector 1 subsector 11."
    assert expected_err in result.stdout or expected_err in result.stderr
    # Config file should not have been updated/created because of transactional safety check
    assert not config_file.exists()


def test_universe_update_handles_custom_universe(monkeypatch, tmp_path: Path):
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    # Mock Stockbit session & universe provider
    import src.infrastructure.browser.stockbit_universe as stockbit_universe
    _fake_client = _mock_authenticated_session(monkeypatch)
    monkeypatch.setattr(stockbit_universe, "StockbitUniverseProvider", MockUniverseProvider)

    # Seed an existing custom universe configuration with metadata
    config_file = tmp_path / "config" / "universes.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    initial_config = {
        "bank": {
            "tickers": ["BBCA"],
            "updated": "2026-06-20",
            "sector_id": 3,
            "subsector_id": 20,
        }
    }
    with open(config_file, "w") as f:
        yaml.dump(initial_config, f)

    # Mock API call for update
    def mock_api_get(self, url: str, params=None):
        if "subsector/20/company" in url:
            return {
                "data": {
                    "companies": [
                        {"ticker": "BBCA", "name": "Bank BCA"},
                        {"ticker": "BBRI", "name": "Bank Mandiri"},
                        {"ticker": "BMRI", "name": "Bank Mandiri"},
                    ]
                }
            }
        return None

    monkeypatch.setattr(_stockbit_api_client.StockbitApiClient, "get", mock_api_get)

    result = runner.invoke(
        app,
        [
            "fetch",
            "universe",
            "update",
            "-u",
            "bank",
            "--config",
            str(config_file),
        ],
    )

    assert result.exit_code == 0
    assert "Updated" in result.stdout

    with open(config_file) as f:
        data = yaml.safe_load(f)

    assert "bank" in data
    # Confirm tickers were updated
    assert data["bank"]["tickers"] == ["BBCA", "BBRI", "BMRI"]
    # Confirm metadata was preserved
    assert data["bank"]["sector_id"] == 3
    assert data["bank"]["subsector_id"] == 20


def test_universe_update_all_includes_custom_universes(monkeypatch, tmp_path: Path):
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    import src.infrastructure.browser.stockbit_universe as stockbit_universe
    _fake_client = _mock_authenticated_session(monkeypatch)
    monkeypatch.setattr(stockbit_universe, "StockbitUniverseProvider", MockUniverseProvider)

    # Seed an existing custom universe configuration with metadata
    config_file = tmp_path / "config" / "universes.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    initial_config = {
        "bank": {
            "tickers": ["BBCA"],
            "updated": "2026-06-20",
            "sector_id": 3,
            "subsector_id": 20,
        }
    }
    with open(config_file, "w") as f:
        yaml.dump(initial_config, f)

    # Mock API call for update
    def mock_api_get(self, url: str, params=None):
        if "subsector/20/company" in url:
            return {
                "data": {
                    "companies": [
                        {"ticker": "BBCA", "name": "Bank BCA"},
                        {"ticker": "BBNI", "name": "Bank BNI"},
                    ]
                }
            }
        return None

    monkeypatch.setattr(_stockbit_api_client.StockbitApiClient, "get", mock_api_get)

    result = runner.invoke(
        app,
        [
            "fetch",
            "universe",
            "update",
            "--config",
            str(config_file),
        ],
    )

    # The command should succeed even if default list_available fetches fail/succeed
    # In MockUniverseProvider list_available returns lq45 & finance, but we mocked
    # exodus get to return None for those, so they will fail (logged as FAILED) but
    # bank will succeed and it will write successful ones.
    assert result.exit_code == 0

    with open(config_file) as f:
        data = yaml.safe_load(f)

    # Confirm bank was updated
    assert data["bank"]["tickers"] == ["BBCA", "BBNI"]
    assert data["bank"]["sector_id"] == 3
    assert data["bank"]["subsector_id"] == 20
