import yaml
import time
from pathlib import Path
from typer.testing import CliRunner
import pytest

from src.adapters.cli.main import app

runner = CliRunner()


def test_universe_create_help():
    result = runner.invoke(app, ["fetch", "universe", "create", "--help"])
    assert result.exit_code == 0
    assert "Create a custom universe from a Stockbit" in result.stdout


class MockBrokerProvider:
    def is_authenticated(self):
        return True

    def _get_token(self):
        return "fake-token"


def test_universe_create_with_subsector(monkeypatch, tmp_path: Path):
    # Setup stockbit profile dir
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    # Mock provider
    import src.infrastructure.browser.playwright_stockbit as playwright_stockbit
    monkeypatch.setattr(playwright_stockbit, "StockbitPlaywrightBrokerProvider", MockBrokerProvider)

    # Mock API call
    def mock_exodus_get(url: str, token: str):
        assert token == "fake-token"
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

    monkeypatch.setattr(playwright_stockbit, "_exodus_get", mock_exodus_get)

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


def test_universe_create_sector_level(monkeypatch, tmp_path: Path):
    # Setup stockbit profile dir
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    # Mock provider
    import src.infrastructure.browser.playwright_stockbit as playwright_stockbit
    monkeypatch.setattr(playwright_stockbit, "StockbitPlaywrightBrokerProvider", MockBrokerProvider)

    # Mock API calls and capture sleep times
    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda secs: sleep_calls.append(secs))

    def mock_exodus_get(url: str, token: str):
        assert token == "fake-token"
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

    monkeypatch.setattr(playwright_stockbit, "_exodus_get", mock_exodus_get)

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

    # Verify sleep pacing occurred between subsectors (1 sleep call since there are 2 subsectors)
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 0.2


def test_universe_create_sector_level_fail_fast(monkeypatch, tmp_path: Path):
    # Setup stockbit profile dir
    (tmp_path / ".stockbit_profile").mkdir()
    monkeypatch.chdir(tmp_path)

    # Mock provider
    import src.infrastructure.browser.playwright_stockbit as playwright_stockbit
    monkeypatch.setattr(playwright_stockbit, "StockbitPlaywrightBrokerProvider", MockBrokerProvider)

    # Mock API calls where the second subsector fetch fails
    def mock_exodus_get(url: str, token: str):
        assert token == "fake-token"
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
            # Fails returning None (e.g. network timeout or 500 error)
            return None
        return None

    monkeypatch.setattr(playwright_stockbit, "_exodus_get", mock_exodus_get)

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
    assert "Error: Failed to fetch data for sector 1 subsector 11." in result.stdout or "Error: Failed to fetch data for sector 1 subsector 11." in result.stderr
    # Config file should not have been updated/created because of transactional safety check
    assert not config_file.exists()
