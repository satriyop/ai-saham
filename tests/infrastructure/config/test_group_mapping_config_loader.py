"""Tests for the group mapping infrastructure loader."""

import yaml

from src.infrastructure.config.group_mapping_config_loader import (
    create_group_mapping_service,
    load_group_mapping,
)


def test_load_group_mapping_reads_yaml(tmp_path):
    config = {
        "groups": {
            "TEST_GROUP": {"name": "Test Conglomerate", "tickers": ["TICK1", "TICK2"]},
        }
    }
    config_path = tmp_path / "groups.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    groups = load_group_mapping(config_path)

    assert groups == config["groups"]


def test_load_group_mapping_missing_file_returns_empty(tmp_path):
    groups = load_group_mapping(tmp_path / "nonexistent.yaml")
    assert groups == {}


def test_load_group_mapping_malformed_yaml_returns_empty(tmp_path):
    config_path = tmp_path / "groups.yaml"
    config_path.write_text("not: [valid: yaml: at all")

    groups = load_group_mapping(config_path)

    assert groups == {}


def test_load_group_mapping_missing_groups_key_returns_empty(tmp_path):
    config_path = tmp_path / "groups.yaml"
    config_path.write_text(yaml.dump({"other_key": {}}))

    groups = load_group_mapping(config_path)

    assert groups == {}


def test_create_group_mapping_service_builds_working_lookup(tmp_path):
    config = {
        "groups": {
            "TEST_GROUP": {"name": "Test Conglomerate", "tickers": ["TICK1"]},
        }
    }
    config_path = tmp_path / "groups.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    service = create_group_mapping_service(config_path)

    assert service.get_group_id("TICK1") == "TEST_GROUP"
