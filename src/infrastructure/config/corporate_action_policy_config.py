"""
Corporate action event-risk policy config — loaded from
config/corporate_action_policy.yaml.

Missing config file falls back to deterministic defaults (identical to the
shipped YAML). Malformed or invalid config (unknown event type, unknown date
role, unknown severity, unknown flag, negative lookback/lookahead windows)
fails loudly with CorporateActionPolicyConfigError, matching the
RulesYamlLoader precedent (missing-file-tolerant, malformed-content-strict).

This module owns YAML parsing/validation only. The policy dataclasses and
error type it returns are application-owned (src/application/dto/corporate_action_policy.py)
so that AssessCorporateActionEventRiskUseCase never imports infrastructure.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.dto.corporate_action_policy import (
    CorporateActionDateRolePolicy,
    CorporateActionEventTypePolicy,
    CorporateActionPolicyConfig,
    CorporateActionPolicyConfigError,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionDateRole,
    CorporateActionType,
)
from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskFlag,
    CorporateActionEventRiskSeverity,
)
from src.infrastructure.config.app_config import APP_CFG

CORPORATE_ACTION_POLICY_CONFIG_PATH = Path(APP_CFG.config_paths.corporate_action_policy)

_KNOWN_EVENT_TYPES = {t.value for t in CorporateActionType}
_KNOWN_DATE_ROLES = {r.value for r in CorporateActionDateRole}
_KNOWN_SEVERITIES = {s.value for s in CorporateActionEventRiskSeverity}
_KNOWN_FLAGS = {f.value for f in CorporateActionEventRiskFlag}

_DEFAULT_POLICY_YAML = """
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
          flags: [price_distortion]
        cum_date:
          severity: warning
          lookback_days: 0
          lookahead_days: 3
          flags: [liquidity_distortion]
    rights_issue:
      enabled: true
      date_roles:
        cum_date:
          severity: warning
          lookback_days: 0
          lookahead_days: 10
          flags: [liquidity_distortion]
        ex_date:
          severity: warning
          lookback_days: 5
          lookahead_days: 10
          flags: [price_distortion, liquidity_distortion]
        trading_start:
          severity: warning
          lookback_days: 10
          lookahead_days: 10
          flags: [liquidity_distortion]
    stock_split:
      enabled: true
      date_roles:
        ex_date:
          severity: warning
          lookback_days: 5
          lookahead_days: 10
          flags: [price_distortion, volume_distortion]
    reverse_split:
      enabled: true
      date_roles:
        ex_date:
          severity: warning
          lookback_days: 5
          lookahead_days: 10
          flags: [price_distortion, volume_distortion]
    bonus:
      enabled: true
      date_roles:
        ex_date:
          severity: warning
          lookback_days: 5
          lookahead_days: 10
          flags: [price_distortion, volume_distortion]
    tender_offer:
      enabled: true
      date_roles:
        offer_start:
          severity: warning
          lookback_days: 0
          lookahead_days: 10
          flags: [special_situation]
        offer_end:
          severity: warning
          lookback_days: 3
          lookahead_days: 10
          flags: [special_situation]
    rups:
      enabled: true
      date_roles:
        rups_date:
          severity: info
          lookback_days: 1
          lookahead_days: 7
          flags: [governance_context]
    pubex:
      enabled: true
      date_roles:
        pubex_date:
          severity: info
          lookback_days: 1
          lookahead_days: 7
          flags: [disclosure_context]
    ipo:
      enabled: true
      date_roles:
        listing_date:
          severity: info
          lookback_days: 30
          lookahead_days: 30
          flags: [new_listing]
"""


def load_corporate_action_policy_config(
    config_path: Path | None = None,
) -> CorporateActionPolicyConfig:
    """Load the corporate action event-risk policy.

    A missing file falls back to the deterministic default policy (identical
    to the shipped config/corporate_action_policy.yaml). A present-but-invalid
    file (bad YAML syntax, unknown event type/date role/severity/flag, or a
    negative lookback/lookahead window) raises CorporateActionPolicyConfigError
    rather than silently falling back.
    """
    path = config_path or CORPORATE_ACTION_POLICY_CONFIG_PATH
    if not path.exists():
        raw = yaml.safe_load(_DEFAULT_POLICY_YAML)
        return _parse_and_validate(raw, source="<default>")

    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise CorporateActionPolicyConfigError(
            f"Invalid YAML syntax in {path}: {exc}"
        ) from exc

    if raw is None:
        raise CorporateActionPolicyConfigError(f"Empty corporate action policy config: {path}")

    return _parse_and_validate(raw, source=str(path))


def _parse_and_validate(raw: object, *, source: str) -> CorporateActionPolicyConfig:
    if not isinstance(raw, dict):
        raise CorporateActionPolicyConfigError(
            f"{source}: config must be a YAML mapping, got {type(raw).__name__}"
        )

    root = raw.get("corporate_action_policy")
    if not isinstance(root, dict):
        raise CorporateActionPolicyConfigError(
            f"{source}: missing required root key 'corporate_action_policy'"
        )

    default_lookback_days = _non_negative_int(
        root, "default_lookback_days", 5, source=source
    )
    default_lookahead_days = _non_negative_int(
        root, "default_lookahead_days", 30, source=source
    )

    raw_event_types = root.get("event_types") or {}
    if not isinstance(raw_event_types, dict):
        raise CorporateActionPolicyConfigError(f"{source}: 'event_types' must be a mapping")

    event_types: dict[str, CorporateActionEventTypePolicy] = {}
    for event_type_key, event_type_cfg in raw_event_types.items():
        if event_type_key not in _KNOWN_EVENT_TYPES:
            raise CorporateActionPolicyConfigError(
                f"{source}: unknown event type '{event_type_key}'. "
                f"Known types: {sorted(_KNOWN_EVENT_TYPES)}"
            )
        if not isinstance(event_type_cfg, dict):
            raise CorporateActionPolicyConfigError(
                f"{source}: event_types.{event_type_key} must be a mapping"
            )

        enabled = event_type_cfg.get("enabled", True)
        if not isinstance(enabled, bool):
            raise CorporateActionPolicyConfigError(
                f"{source}: event_types.{event_type_key}.enabled must be a boolean"
            )

        raw_date_roles = event_type_cfg.get("date_roles") or {}
        if not isinstance(raw_date_roles, dict):
            raise CorporateActionPolicyConfigError(
                f"{source}: event_types.{event_type_key}.date_roles must be a mapping"
            )

        date_roles: dict[str, CorporateActionDateRolePolicy] = {}
        for date_role_key, date_role_cfg in raw_date_roles.items():
            context = f"event_types.{event_type_key}.date_roles.{date_role_key}"
            if date_role_key not in _KNOWN_DATE_ROLES:
                raise CorporateActionPolicyConfigError(
                    f"{source}: unknown date role '{date_role_key}' under "
                    f"event_types.{event_type_key}. Known roles: {sorted(_KNOWN_DATE_ROLES)}"
                )
            if not isinstance(date_role_cfg, dict):
                raise CorporateActionPolicyConfigError(f"{source}: {context} must be a mapping")

            severity_raw = date_role_cfg.get("severity")
            if severity_raw not in _KNOWN_SEVERITIES:
                raise CorporateActionPolicyConfigError(
                    f"{source}: unknown severity '{severity_raw}' at {context}. "
                    f"Known severities: {sorted(_KNOWN_SEVERITIES)}"
                )

            lookback_days = _non_negative_int(
                date_role_cfg, "lookback_days", 0, source=source, context=context
            )
            lookahead_days = _non_negative_int(
                date_role_cfg, "lookahead_days", 0, source=source, context=context
            )

            raw_flags = date_role_cfg.get("flags") or []
            if not isinstance(raw_flags, list):
                raise CorporateActionPolicyConfigError(f"{source}: {context}.flags must be a list")

            flags: list[CorporateActionEventRiskFlag] = []
            for flag_raw in raw_flags:
                if flag_raw not in _KNOWN_FLAGS:
                    raise CorporateActionPolicyConfigError(
                        f"{source}: unknown flag '{flag_raw}' at {context}. "
                        f"Known flags: {sorted(_KNOWN_FLAGS)}"
                    )
                flags.append(CorporateActionEventRiskFlag(flag_raw))

            date_roles[date_role_key] = CorporateActionDateRolePolicy(
                severity=CorporateActionEventRiskSeverity(severity_raw),
                lookback_days=lookback_days,
                lookahead_days=lookahead_days,
                flags=tuple(flags),
            )

        event_types[event_type_key] = CorporateActionEventTypePolicy(
            enabled=enabled,
            date_roles=date_roles,
        )

    return CorporateActionPolicyConfig(
        default_lookback_days=default_lookback_days,
        default_lookahead_days=default_lookahead_days,
        event_types=event_types,
    )


def _non_negative_int(
    data: dict,
    key: str,
    default: int,
    *,
    source: str,
    context: str | None = None,
) -> int:
    if key not in data:
        return default
    value = data[key]
    label = f"{context}.{key}" if context else key
    if not isinstance(value, int) or isinstance(value, bool):
        raise CorporateActionPolicyConfigError(
            f"{source}: {label} must be an integer, got {type(value).__name__}"
        )
    if value < 0:
        raise CorporateActionPolicyConfigError(f"{source}: {label} must be >= 0, got {value}")
    return value
