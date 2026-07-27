from pathlib import Path

import yaml

from src.infrastructure.config.swing_policy_config_gateway import (
    YamlSwingPolicyConfigGateway,
)


def test_gateway_applies_exact_allowlisted_change_and_rereads(tmp_path: Path) -> None:
    path = tmp_path / "config" / "signal_engine.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump({"signal_engine": {"classification": {"strong_min_score": 70}}}))
    gateway = YamlSwingPolicyConfigGateway(
        tmp_path,
        policy_files=("config/signal_engine.yaml",),
        dirty_checker=lambda _root, _path: False,
    )
    before = gateway.read_snapshot()
    changes = {"config/signal_engine.yaml:signal_engine.classification.strong_min_score": 68}

    assert gateway.target_files_clean(changes) is True
    gateway.apply_changes(changes)
    after = gateway.read_snapshot()

    assert before.config_hash != after.config_hash
    assert after.values == {**before.values, **changes}


def test_gateway_reports_dirty_target(tmp_path: Path) -> None:
    path = tmp_path / "config" / "signal_engine.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump({"signal_engine": {"threshold": 70}}))
    gateway = YamlSwingPolicyConfigGateway(
        tmp_path,
        policy_files=("config/signal_engine.yaml",),
        dirty_checker=lambda _root, _path: True,
    )

    assert (
        gateway.target_files_clean({"config/signal_engine.yaml:signal_engine.threshold": 68})
        is False
    )
