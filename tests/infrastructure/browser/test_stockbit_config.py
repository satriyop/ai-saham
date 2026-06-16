"""Tests for _StockbitConfig YAML loader in playwright_stockbit."""

from pathlib import Path

import pytest
import yaml

from src.infrastructure.browser.playwright_stockbit import (
    _StockbitConfig,
    _load_stockbit_config,
    _INSTITUTIONAL_PROXY_CODES,
    TRACKED_BROKER_CODES,
    _IEV_MOVER_URL_MAIN,
    _ORDER_BOOK_API,
)


def _write_yaml(path: Path, data: dict) -> Path:
    with open(path, "w") as fh:
        yaml.dump(data, fh)
    return path


# ── Loader unit tests ─────────────────────────────────────────────────────

def test_loads_tracked_broker_codes_from_yaml(tmp_path):
    cfg_file = _write_yaml(tmp_path / "stockbit.yaml", {
        "broker_codes": {"tracked": ["AK", "ZP"]},
        "endpoints": {},
    })
    result = _load_stockbit_config(cfg_file)
    assert result.tracked_broker_codes == ("AK", "ZP")


def test_loads_institutional_proxy_codes_from_yaml(tmp_path):
    cfg_file = _write_yaml(tmp_path / "stockbit.yaml", {
        "broker_codes": {"institutional_proxy": ["BK", "YU"]},
        "endpoints": {},
    })
    result = _load_stockbit_config(cfg_file)
    assert result.institutional_proxy_codes == ("BK", "YU")


def test_loads_endpoint_url_from_yaml(tmp_path):
    custom_url = "https://example.stockbit.com/custom-orderbook/{ticker}"
    cfg_file = _write_yaml(tmp_path / "stockbit.yaml", {
        "endpoints": {"orderbook": {"url": custom_url}},
        "broker_codes": {},
    })
    result = _load_stockbit_config(cfg_file)
    assert result.orderbook_url == custom_url


def test_falls_back_to_defaults_when_file_missing():
    result = _load_stockbit_config(Path("/nonexistent/does-not-exist.yaml"))
    assert result == _StockbitConfig()


def test_falls_back_to_defaults_when_yaml_invalid(tmp_path):
    bad = tmp_path / "stockbit.yaml"
    bad.write_text("{ bad yaml: :")
    result = _load_stockbit_config(bad)
    assert result == _StockbitConfig()


def test_falls_back_to_defaults_when_codes_list_empty(tmp_path):
    cfg_file = _write_yaml(tmp_path / "stockbit.yaml", {
        "broker_codes": {"tracked": []},
        "endpoints": {},
    })
    result = _load_stockbit_config(cfg_file)
    # Empty list → fall back to hardcoded defaults (never leave codes empty)
    assert result.tracked_broker_codes == _StockbitConfig().tracked_broker_codes


def test_strips_and_uppercases_broker_codes(tmp_path):
    cfg_file = _write_yaml(tmp_path / "stockbit.yaml", {
        "broker_codes": {"tracked": ["ak", " zp "]},
        "endpoints": {},
    })
    result = _load_stockbit_config(cfg_file)
    assert result.tracked_broker_codes == ("AK", "ZP")


def test_partial_yaml_uses_defaults_for_missing_keys(tmp_path):
    """Only tracked codes provided; institutional_proxy should stay at defaults."""
    cfg_file = _write_yaml(tmp_path / "stockbit.yaml", {
        "broker_codes": {"tracked": ["AK"]},
    })
    result = _load_stockbit_config(cfg_file)
    assert result.tracked_broker_codes == ("AK",)
    assert result.institutional_proxy_codes == _StockbitConfig().institutional_proxy_codes


def test_live_config_loads_without_error():
    """Smoke test: the actual config/stockbit.yaml is valid and parseable."""
    result = _load_stockbit_config(Path("config/stockbit.yaml"))
    assert len(result.tracked_broker_codes) > 0
    assert len(result.institutional_proxy_codes) > 0
    assert result.iev_movers_main_url.startswith("https://")
    assert result.orderbook_url.startswith("https://")
    assert "{ticker}" in result.orderbook_url


# ── Module-level constants wired correctly ────────────────────────────────

def test_module_constants_are_populated():
    """Constants loaded at module import should match the live YAML values."""
    assert "AK" in _INSTITUTIONAL_PROXY_CODES
    assert "AK" in TRACKED_BROKER_CODES
    assert "MOVER_TYPE_IEV_TOP_GAINER" in _IEV_MOVER_URL_MAIN
    assert "{ticker}" in _ORDER_BOOK_API
