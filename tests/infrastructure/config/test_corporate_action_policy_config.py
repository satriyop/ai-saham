"""Tests for corporate action event-risk policy config loading.

Missing-file-tolerant, malformed-content-strict (mirrors RulesYamlLoader
precedent). Layer: Infrastructure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskFlag,
    CorporateActionEventRiskSeverity,
)
from src.infrastructure.config.corporate_action_policy_config import (
    CorporateActionPolicyConfigError,
    load_corporate_action_policy_config,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SHIPPED_CONFIG_PATH = REPO_ROOT / "config" / "corporate_action_policy.yaml"


def test_missing_file_falls_back_to_deterministic_defaults(tmp_path):
    missing_path = tmp_path / "does_not_exist.yaml"

    cfg = load_corporate_action_policy_config(config_path=missing_path)

    assert cfg.default_lookback_days == 5
    assert cfg.default_lookahead_days == 30

    dividend_ex = cfg.resolve("dividend", "ex_date")
    assert dividend_ex is not None
    assert dividend_ex.severity == CorporateActionEventRiskSeverity.WARNING
    assert CorporateActionEventRiskFlag.PRICE_DISTORTION in dividend_ex.flags
    assert dividend_ex.lookback_days == 2
    assert dividend_ex.lookahead_days == 5

    rups_policy = cfg.resolve("rups", "rups_date")
    assert rups_policy is not None
    assert rups_policy.severity == CorporateActionEventRiskSeverity.INFO


def test_default_max_lookback_and_lookahead_days(tmp_path):
    missing_path = tmp_path / "does_not_exist.yaml"

    cfg = load_corporate_action_policy_config(config_path=missing_path)

    # Max lookback across all default date roles: ipo.listing_date has the
    # largest configured lookback_days (30); max lookahead is also 30
    # (default_lookahead_days / ipo.listing_date / dividend/rights_issue tie).
    assert cfg.max_lookback_days() == 30
    assert cfg.max_lookahead_days() == 30


def test_shipped_config_yaml_parses_without_error_and_matches_expected_values():
    cfg = load_corporate_action_policy_config(config_path=SHIPPED_CONFIG_PATH)

    assert cfg.default_lookback_days == 5
    assert cfg.default_lookahead_days == 30

    dividend_ex = cfg.resolve("dividend", "ex_date")
    assert dividend_ex is not None
    assert dividend_ex.severity == CorporateActionEventRiskSeverity.WARNING
    assert dividend_ex.lookback_days == 2
    assert dividend_ex.lookahead_days == 5
    assert dividend_ex.flags == (CorporateActionEventRiskFlag.PRICE_DISTORTION,)

    rups_policy = cfg.resolve("rups", "rups_date")
    assert rups_policy is not None
    assert rups_policy.severity == CorporateActionEventRiskSeverity.INFO
    assert rups_policy.lookback_days == 1
    assert rups_policy.lookahead_days == 7
    assert rups_policy.flags == (CorporateActionEventRiskFlag.GOVERNANCE_CONTEXT,)

    tender_offer_start = cfg.resolve("tender_offer", "offer_start")
    assert tender_offer_start is not None
    assert tender_offer_start.severity == CorporateActionEventRiskSeverity.WARNING
    assert tender_offer_start.lookback_days == 0
    assert tender_offer_start.lookahead_days == 10
    assert tender_offer_start.flags == (CorporateActionEventRiskFlag.SPECIAL_SITUATION,)

    tender_offer_end = cfg.resolve("tender_offer", "offer_end")
    assert tender_offer_end is not None
    assert tender_offer_end.lookback_days == 3
    assert tender_offer_end.lookahead_days == 10


def test_shipped_config_no_config_path_argument_loads_shipped_default_path():
    # No config_path -> module constant CORPORATE_ACTION_POLICY_CONFIG_PATH,
    # which resolves to config/corporate_action_policy.yaml relative to the
    # repo root. This only holds true when run from the repo root (as pytest
    # is invoked in this repo's CI/dev workflow), so we additionally assert
    # equivalence with explicitly passing the shipped path.
    cfg_explicit = load_corporate_action_policy_config(config_path=SHIPPED_CONFIG_PATH)
    cfg_default_arg = load_corporate_action_policy_config()

    assert cfg_default_arg.resolve("dividend", "ex_date") == cfg_explicit.resolve(
        "dividend", "ex_date"
    )
    assert cfg_default_arg.max_lookback_days() == cfg_explicit.max_lookback_days()
    assert cfg_default_arg.max_lookahead_days() == cfg_explicit.max_lookahead_days()


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "corporate_action_policy.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_unknown_event_type_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: 5
  default_lookahead_days: 30
  event_types:
    foobar_event:
      enabled: true
      date_roles:
        ex_date:
          severity: warning
          lookback_days: 2
          lookahead_days: 5
          flags: [price_distortion]
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="unknown event type"):
        load_corporate_action_policy_config(config_path=path)


def test_unknown_date_role_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: 5
  default_lookahead_days: 30
  event_types:
    dividend:
      enabled: true
      date_roles:
        made_up_role:
          severity: warning
          lookback_days: 2
          lookahead_days: 5
          flags: [price_distortion]
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="unknown date role"):
        load_corporate_action_policy_config(config_path=path)


def test_unknown_severity_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: 5
  default_lookahead_days: 30
  event_types:
    dividend:
      enabled: true
      date_roles:
        ex_date:
          severity: catastrophic
          lookback_days: 2
          lookahead_days: 5
          flags: [price_distortion]
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="unknown severity"):
        load_corporate_action_policy_config(config_path=path)


def test_unknown_flag_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: 5
  default_lookahead_days: 30
  event_types:
    dividend:
      enabled: true
      date_roles:
        ex_date:
          severity: warning
          lookback_days: 2
          lookahead_days: 5
          flags: [made_up_flag]
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="unknown flag"):
        load_corporate_action_policy_config(config_path=path)


def test_negative_lookback_days_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: 5
  default_lookahead_days: 30
  event_types:
    dividend:
      enabled: true
      date_roles:
        ex_date:
          severity: warning
          lookback_days: -1
          lookahead_days: 5
          flags: [price_distortion]
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="lookback_days"):
        load_corporate_action_policy_config(config_path=path)


def test_negative_lookahead_days_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: 5
  default_lookahead_days: 30
  event_types:
    dividend:
      enabled: true
      date_roles:
        ex_date:
          severity: warning
          lookback_days: 2
          lookahead_days: -5
          flags: [price_distortion]
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="lookahead_days"):
        load_corporate_action_policy_config(config_path=path)


def test_negative_default_lookback_days_raises(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: -5
  default_lookahead_days: 30
  event_types: {}
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="default_lookback_days"):
        load_corporate_action_policy_config(config_path=path)


def test_malformed_yaml_syntax_raises_wrapped_error(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
corporate_action_policy:
  default_lookback_days: 5
  event_types:
    dividend:
      enabled: true
      date_roles: [unbalanced: [nested, brackets
""",
    )

    with pytest.raises(CorporateActionPolicyConfigError, match="Invalid YAML syntax"):
        load_corporate_action_policy_config(config_path=path)
